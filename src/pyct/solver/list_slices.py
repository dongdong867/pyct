"""Positions into a tracked list, and slices of one, as Python reads them.

A negative position counts back from the end; a slice's bounds are clamped to the list, and a
step of -1 runs back from its start (Python's `PySlice_AdjustIndices`). Each clamp that the
path's own facts do not settle is written once, ``(define-fun p!N () Int ...)``, and named
wherever it is read.
"""

from __future__ import annotations

from collections.abc import Callable

from pyct.core.branch import Expression
from pyct.solver.list_kinds import Kinds
from pyct.solver.list_terms import Lin, Piece, Window


class Slices:
    """Positions and slices of one path's lists: each term it defined, and the least value each
    named term takes on the path.

    ``named`` is render's term of a part, ``definitions`` render's own list, and ``positions``
    each tracked position or bound, whose value the answer reads.
    """

    def __init__(self) -> None:
        self.named: Callable[[Expression], str] = str
        self.definitions: list[str] = []
        self.least: dict[str, int] = {}
        # each term a position, a bound or a read defined, by its text, and the name it has
        self.written: dict[str, str] = {}
        self.positions: dict[int, Expression] = {}

    def window(self, base: Piece, bounds: list[Expression], kinds: Kinds) -> Window:
        """A slice of ``base``, clamped to it as Python clamps it; a step of -1 runs back from
        its start."""
        size = base.length
        start_bound, stop_bound = (self._bound(part) for part in bounds[:2])
        if len(bounds) > 2 and bounds[2] == -1:
            start = self._back(start_bound, size, size.minus(Lin(1)))
            stop = self._back(stop_bound, size, Lin(-1))
            length, step = self._nonnegative(start.minus(stop)), -1
        else:
            start = self._clamped(start_bound, size, Lin())
            stop = self._clamped(stop_bound, size, size)
            length = (
                size.minus(start) if stop_bound is None else self._nonnegative(stop.minus(start))
            )
            step = 1
        return Window(length, kinds.kinds, kinds.every, base=base, start=start, step=step)

    def position(self, part: Expression, piece: Piece) -> Lin:
        """The position an item is read at: from the start, back from the end for a negative
        number, and a tracked index counted back from the end when it is negative."""
        bound = self._bound(part)
        assert bound is not None
        number = bound.number()
        if number is not None:
            return bound if number >= 0 else piece.length.plus(bound)
        value, length = bound.text(), piece.length.text()
        return self._defined(f"(ite (< {value} 0) (+ {value} {length}) {value})", nonnegative=False)

    def _bound(self, part: Expression) -> Lin | None:
        """A slice bound or a position as a term: a number, None for a missing bound, or a
        tracked int's term, whose value the answer reads."""
        if part is None:
            return None
        if type(part) is int:
            return Lin(part)
        self.positions[id(part)] = part
        return Lin.of(self.named(part))

    def _clamped(self, bound: Lin | None, size: Lin, missing: Lin) -> Lin:
        """A bound of a step-1 slice as Python clamps it: counted back from the end when
        negative, then kept between 0 and the length. A number the list's least length
        settles is the bound as written, or counted back."""
        if bound is None:
            return missing
        number, shortest = bound.number(), size.lowest(self.least)
        if number is not None and shortest is not None and shortest >= abs(number):
            return bound if number >= 0 else size.plus(bound)
        if number == 0:
            return Lin()
        value, length = bound.text(), size.text()
        counted = f"(ite (< (+ {value} {length}) 0) 0 (+ {value} {length}))"
        clamped = f"(ite (< {value} 0) {counted} (ite (> {value} {length}) {length} {value}))"
        return self._defined(clamped, nonnegative=True)

    def _back(self, bound: Lin | None, size: Lin, missing: Lin) -> Lin:
        """A bound of a step -1 slice as Python clamps it: counted back from the end when
        negative, -1 when that is still before the start, and the last position past the end.
        A number the list's least length settles is the bound as written, or counted back."""
        if bound is None:
            return missing
        number, shortest = bound.number(), size.lowest(self.least)
        if number is not None and shortest is not None:
            if 0 <= number < shortest:
                return bound
            if number < 0 and shortest >= -number:
                return size.plus(bound)
        value, length = bound.text(), size.text()
        counted = f"(ite (< (+ {value} {length}) 0) (- 1) (+ {value} {length}))"
        clamped = (
            f"(ite (< {value} 0) {counted} (ite (>= {value} {length}) (- {length} 1) {value}))"
        )
        return self._defined(clamped, nonnegative=False)

    def _nonnegative(self, difference: Lin) -> Lin:
        """``max(0, difference)``: a slice's length from its clamped bounds."""
        least = difference.lowest(self.least)
        if least is not None and least >= 0:
            return difference
        text = difference.text()
        return self._defined(f"(ite (< {text} 0) 0 {text})", nonnegative=True)

    def _defined(self, text: str, *, nonnegative: bool) -> Lin:
        """A term written once, as ``(define-fun p!N () Int ...)``, and named wherever read.

        Slices with the same bounds on one list clamp them the same way, so a term already
        written is named again rather than defined twice.
        """
        if text not in self.written:
            name = f"p!{len(self.definitions)}"
            self.definitions.append(f"(define-fun {name} () Int {text})")
            self.written[text] = name
            if nonnegative:
                self.least[name] = 0
        return Lin.of(self.written[text])

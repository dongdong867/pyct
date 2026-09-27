"""Positions into a tracked list, and slices of one, as Python reads them.

A negative position counts back from the end; a slice's bounds are clamped to the list, and a
step of -1 runs back from its start (Python's `PySlice_AdjustIndices`). Each clamp that the
path's own facts do not settle is written once, ``(define-fun p!N () Int ...)``, and named
wherever it is read.

A list cut at slices again and again, `items[1:2] = [x]` in a loop say, reads each version of
itself at two positions that differ by such a clamp, so a read of it doubles with each cut.
When ``settle`` is set, each clamp the input whose path this is settles goes the way it went
there: the program asserts the input's side of each (`len(items) >= 2`) and the clamp is the
bound as written, so the cuts read through in a row. Those assertions narrow the answers the
solver may give, which is why an unsat answer under them is only an unknown (see
``Program.narrowed``).
"""

from __future__ import annotations

from collections.abc import Callable

from pyct.core.branch import Expression
from pyct.solver.list_kinds import Kinds
from pyct.solver.list_terms import FALSE, TRUE, Lin, Piece, Window, compare


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
        # each named term's value in the input whose path this is, where it is known, whether
        # clamps go the way they went there, and what that asserts
        self.origin: dict[str, int] = {}
        self.settle = False
        self.regime: dict[str, None] = {}
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
        length = self.length_of(part)
        if length is not None:
            return length
        self.positions[id(part)] = part
        linear = self._linear(part, _LINEAR_DEPTH)
        return Lin.of(self.named(part)) if linear is None else linear

    def _linear(self, part: Expression, depth: int) -> Lin | None:
        """A bound written as a sum of leaves and numbers, `i + 1` say, as that sum, so the
        input's values settle its clamp; None for any other, or one nested past ``depth``."""
        if isinstance(part, int) and not isinstance(part, bool):
            return Lin(part)
        term = self.named(part) if not isinstance(part, list) or depth else ""
        if term.startswith("|"):
            return Lin.of(term)
        if not isinstance(part, list) or not depth or part[0] not in ("+", "-", "*"):
            return None
        operands = [self._linear(operand, depth - 1) for operand in part[1:]]
        summed = [operand for operand in operands if operand is not None]
        return _combined(str(part[0]), summed) if len(summed) == len(operands) else None

    def length_of(self, part: Expression) -> Lin | None:
        """A bound that is a list's length, ``len(items[a:b])`` in a slice deletion, as that
        list's own length term; None for any other bound."""
        return None

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
        settled = self._settled(bound, size, back=False)
        if settled is not None:
            return settled
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
        settled = self._settled(bound, size, back=True)
        if settled is not None:
            return settled
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
        was = self.origin_of(difference) if self.settle else None
        if was is not None:
            self._hold(Lin(), difference, or_equal=True, swap=was < 0)
            return difference if was >= 0 else Lin()
        text = difference.text()
        return self._defined(f"(ite (< {text} 0) 0 {text})", nonnegative=True)

    def origin_of(self, term: Lin) -> int | None:
        """A term's value in the input whose path this is, when each named term's is known."""
        if any(atom not in self.origin for atom, _ in term.atoms):
            return None
        return term.const + sum(factor * self.origin[atom] for atom, factor in term.atoms)

    def _settled(self, bound: Lin, size: Lin, *, back: bool) -> Lin | None:
        """A clamp as it went in the input whose path this is, with the program asserting it
        goes that way; None when not settling, or when that input's values are not known."""
        if not self.settle:
            return None
        was, length = self.origin_of(bound), self.origin_of(size)
        if was is None or length is None:
            return None
        if was >= 0:
            inside = was < length if back else was <= length
            self._hold(Lin(), bound, or_equal=True)
            self._hold(bound, size, or_equal=not back, swap=not inside)
            if inside:
                return bound
            return size.minus(Lin(1)) if back else size
        counted = size.plus(bound)
        self._hold(bound, Lin(), or_equal=False)
        self._hold(Lin(), counted, or_equal=True, swap=was + length < 0)
        if was + length >= 0:
            return counted
        return Lin(-1) if back else Lin()

    def _hold(self, low: Lin, high: Lin, *, or_equal: bool, swap: bool = False) -> None:
        """Assert ``low < high``, ``low <= high``, or with ``swap`` its negation, the side the
        input took; one the path's facts already settle asserts nothing."""
        written = compare(low, high, self.least, or_equal=or_equal)
        if written == TRUE and not swap or written == FALSE and swap:
            return
        self.regime[f"(assert (not {written}))" if swap else f"(assert {written})"] = None

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


# how deep a bound's sum may nest and still be read as one
_LINEAR_DEPTH = 8


def _combined(head: str, operands: list[Lin]) -> Lin | None:
    """``+``, ``-`` or ``*`` of sums, as a sum: a product only by a number."""
    if head == "-" and len(operands) == 1:
        return operands[0].times(-1)
    first, second = operands
    if head == "+":
        return first.plus(second)
    if head == "-":
        return first.minus(second)
    number = first.number() if first.number() is not None else second.number()
    other = second if first.number() is not None else first
    return None if number is None else other.times(number)

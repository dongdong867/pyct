"""A tracked list as cvc5 reads it: a length, and each item read by splitting the list at the
pieces it was built from (lists-and-dicts-as-arrays-with-a-length).

An argument's list is an ``Int`` length and one array per kind of item. A list the target built
from it is a tree of the pieces Python joined: a display of items, two lists joined, a window a
slice cut, a list repeated. A read at a position walks that tree with ``ite``, one branch per
piece the position can land in, so the program holds no store and no sequence. A position is
kept as a sum of named terms and a number, so the pieces it cannot reach are left out before
any term is written: after 3,000 appends, ``out[3]`` reaches five pieces and ``out[-1]`` one.

Every item keeps its kind, so a read of an int is a read of the int array, and when the list
also holds items of other kinds the read carries a guard: where the position lands, the item is
of the kind the target read.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from pyct.binding.shapes import ListShape

# a term that holds, and one that does not
TRUE, FALSE = "true", "false"


@dataclass(frozen=True)
class Lin:
    """An Int term as a number plus named terms, each times a number: ``n + 3``, ``n - s``.

    Two positions that differ by a number compare without the solver, which is what leaves
    out the pieces a read cannot reach.
    """

    const: int = 0
    atoms: tuple[tuple[str, int], ...] = ()

    @classmethod
    def of(cls, term: str) -> Lin:
        return cls(0, ((term, 1),))

    def plus(self, other: Lin, times: int = 1) -> Lin:
        """This term plus ``times`` the other."""
        atoms = dict(self.atoms)
        for term, factor in other.atoms:
            atoms[term] = atoms.get(term, 0) + factor * times
        kept = tuple(sorted((term, factor) for term, factor in atoms.items() if factor))
        return Lin(self.const + other.const * times, kept)

    def minus(self, other: Lin) -> Lin:
        return self.plus(other, -1)

    def times(self, factor: int) -> Lin:
        return Lin(0).plus(self, factor)

    def number(self) -> int | None:
        """The term's value when it holds no named term."""
        return None if self.atoms else self.const

    def text(self) -> str:
        """The term as SMT-LIB writes it."""
        parts = [_scaled(term, factor) for term, factor in self.atoms]
        if self.const or not parts:
            parts.append(_number(self.const))
        return parts[0] if len(parts) == 1 else f"(+ {' '.join(parts)})"

    def lowest(self, nonnegative: set[str]) -> int | None:
        """The least the term can be, when each named term it adds is one known not negative."""
        if any(factor < 0 or term not in nonnegative for term, factor in self.atoms):
            return None
        return self.const

    def highest(self, nonnegative: set[str]) -> int | None:
        """The most the term can be, when each named term it takes away is one known not
        negative."""
        if any(factor > 0 or term not in nonnegative for term, factor in self.atoms):
            return None
        return self.const


def _number(value: int) -> str:
    return f"(- {-value})" if value < 0 else str(value)


def _scaled(term: str, factor: int) -> str:
    return term if factor == 1 else f"(* {_number(factor)} {term})"


@dataclass
class Piece:
    """A list as cvc5 reads it: its length, and the kinds of the items it can hand out.

    ``kinds`` are the kinds of the items the input and the target put in it, as core counts
    them to tell a read's kind; ``every`` adds the kinds of items the solver may add.
    """

    length: Lin
    kinds: frozenset[str]
    every: frozenset[str]


@dataclass
class Stored(Piece):
    """An argument's list, or a list inside one: an array per kind, read at a position."""

    arrays: Callable[[str], str] = field(default=lambda kind: kind)
    shape: ListShape = field(default_factory=lambda: ListShape(()))


@dataclass
class Shown(Piece):
    """A list display: each item's term, or None for an item the solver does not read, and its
    kind."""

    items: list[tuple[str | None, str]] = field(default_factory=list)


@dataclass
class Joined(Piece):
    """Lists joined by `+`, or one repeated by `*`, in order."""

    parts: list[Piece] = field(default_factory=list)


@dataclass
class Window(Piece):
    """A slice of a list: its position ``q`` reads the list at ``start + q``, or ``start - q``
    for a step of -1."""

    base: Piece = field(default_factory=lambda: Shown(Lin(), frozenset(), frozenset()))
    start: Lin = field(default_factory=Lin)
    step: int = 1


@dataclass(frozen=True)
class Read:
    """What reading one position gives: the item's term, or None where no item of the kind
    read can be, and when the item there is of that kind."""

    value: str | None
    guard: str


def compare(low: Lin, high: Lin, nonnegative: set[str], *, or_equal: bool = False) -> str:
    """``low < high``, or ``low <= high``, decided here when the difference says."""
    difference = high.minus(low)
    least = difference.lowest(nonnegative)
    most = difference.highest(nonnegative)
    if least is not None and (least > 0 or (or_equal and least >= 0)):
        return TRUE
    if most is not None and (most < 0 or (not or_equal and most <= 0)):
        return FALSE
    op = "<=" if or_equal else "<"
    return f"({op} {low.text()} {high.text()})"


def ite(condition: str, then: str, otherwise: str) -> str:
    if condition == TRUE or then == otherwise:
        return then
    if condition == FALSE:
        return otherwise
    return f"(ite {condition} {then} {otherwise})"


def either(one: str, other: str) -> str:
    if TRUE in (one, other):
        return TRUE
    if one == FALSE:
        return other
    return one if other == FALSE else f"(or {one} {other})"


def both(one: str, other: str) -> str:
    if FALSE in (one, other):
        return FALSE
    if one == TRUE:
        return other
    return one if other == TRUE else f"(and {one} {other})"


def stored_guard(piece: Stored, position: Lin, kind: str, nonnegative: set[str]) -> str:
    """Where an argument's list holds an item of ``kind`` at ``position``: the runs of the input
    that hold that kind, and past the input when an added item is of it."""
    if piece.every == {kind}:
        return TRUE
    guard = FALSE
    for run_kind, start, stop in piece.shape.runs():
        if run_kind == kind:
            within = both(
                compare(Lin(start), position, nonnegative, or_equal=True),
                compare(position, Lin(stop), nonnegative),
            )
            guard = either(guard, within)
    if piece.shape.fill == kind:
        added = compare(Lin(len(piece.shape.kinds)), position, nonnegative, or_equal=True)
        guard = either(guard, added)
    return guard


def read(piece: Piece, position: Lin, kind: str, nonnegative: set[str]) -> Read:
    """The item of ``kind`` at ``position``, split at the pieces the position can land in.

    The tree of pieces is walked with a stack of its own, since a list the target changed
    thousands of times is that many levels deep.
    """
    found = _Reader(kind, nonnegative).read(piece, position)
    # a list whose every item is of the kind read needs no guard: the path keeps the position
    # inside the list, and any item there is of that kind
    return Read(found.value, TRUE) if piece.every <= {kind} else found


# one step of a read: a piece to read at a position, or the branches to put back together
type _Task = tuple[Piece, Lin] | tuple[None, list[str]]


class _Reader:
    """One read, its pieces walked on a stack of its own and put back together as they finish."""

    def __init__(self, kind: str, nonnegative: set[str]) -> None:
        self.kind = kind
        self.nonnegative = nonnegative

    def read(self, piece: Piece, position: Lin) -> Read:
        tasks: list[_Task] = [(piece, position)]
        done: list[Read] = []
        while tasks:
            task = tasks.pop()
            if task[0] is None:
                conditions = task[1]
                parts = [done.pop() for _ in range(len(conditions) + 1)][::-1]
                done.append(_chosen(conditions, parts))
                continue
            branches = self._branches(task[0], task[1])
            if isinstance(branches, Read):
                done.append(branches)
                continue
            conditions, parts = branches
            tasks.append((None, conditions))
            tasks.extend(reversed(parts))
        return done[0]

    def _branches(
        self, piece: Piece, position: Lin
    ) -> Read | tuple[list[str], list[tuple[Piece, Lin]]]:
        """A read that ends at this piece, or the pieces it goes on into and when each."""
        if isinstance(piece, Stored):
            return self._stored(piece, position)
        if isinstance(piece, Shown):
            return self._shown(piece, position)
        if isinstance(piece, Window):
            moved = piece.start.plus(position, piece.step)
            return [], [(piece.base, moved)]
        assert isinstance(piece, Joined)
        return self._joined(piece, position)

    def _stored(self, piece: Stored, position: Lin) -> Read:
        guard = stored_guard(piece, position, self.kind, self.nonnegative)
        if self.kind not in piece.every:
            return Read(None, FALSE)
        return Read(f"(select {piece.arrays(self.kind)} {position.text()})", guard)

    def _shown(self, piece: Shown, position: Lin) -> Read:
        """A display: the item the position is, each one a branch."""
        value, guard = None, FALSE
        for at in reversed(range(len(piece.items))):
            here = _equal(position, at, self.nonnegative)
            if here == FALSE:
                continue
            term, item_kind = piece.items[at]
            fits = term is not None and item_kind == self.kind
            if fits:
                value = term if value is None else ite(here, term, value)  # type: ignore[arg-type]
            guard = ite(here, TRUE if fits else FALSE, guard)
        every = all(term is not None and kind == self.kind for term, kind in piece.items)
        return Read(value, TRUE if every else guard)

    def _joined(self, piece: Joined, position: Lin) -> Read | tuple[list[str], list[tuple[Piece, Lin]]]:
        """Joined lists: the part the position lands in, each part a branch taken when the
        position is before its end, those it cannot reach left out."""
        conditions: list[str] = []
        parts: list[tuple[Piece, Lin]] = []
        offset = Lin()
        for part in piece.parts:
            end = offset.plus(part.length)
            before_end = compare(position, end, self.nonnegative)
            if before_end != FALSE:
                parts.append((part, position.minus(offset)))
                if before_end == TRUE:
                    break
                conditions.append(before_end)
            offset = end
        if not parts:
            return Read(None, FALSE)
        # the last part reached is the branch taken when every condition before it failed
        return conditions[: len(parts) - 1], parts


def _equal(position: Lin, at: int, nonnegative: set[str]) -> str:
    """``position == at``, decided here when the difference says."""
    below = compare(position, Lin(at), nonnegative)
    above = compare(Lin(at), position, nonnegative)
    if FALSE == below == above:
        return TRUE
    if TRUE in (below, above):
        return FALSE
    return f"(= {position.text()} {at})"


def _chosen(conditions: list[str], parts: list[Read]) -> Read:
    """Branches put back together: the first part whose condition holds, the last one else.

    A branch where no item of the kind read can be is left out of the value and turns its
    guard false, so the solver keeps the position away from it.
    """
    value = parts[-1].value
    guard = parts[-1].guard if value is not None else FALSE
    for condition, part in zip(reversed(conditions), reversed(parts[:-1]), strict=True):
        part_guard = part.guard if part.value is not None else FALSE
        if part.value is not None:
            value = part.value if value is None else ite(condition, part.value, value)
        guard = ite(condition, part_guard, guard)
    return Read(value, guard)

"""A tracked list as cvc5 reads it: a length, and the pieces it was built from
(containers-arrays-counted-keys-and-read-places).

An argument's list is an ``Int`` length and one array per kind of item. A list the target built
from it is a tree of the pieces Python joined: a display of items, two lists joined, a window a
slice cut, a list repeated. A position is kept as a sum of named terms and a number, and each
named term with the least value the path lets it take, so pieces a read cannot reach are left
out before any term is written (see ``list_reads``).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field

from pyct.binding.shapes import ListShape

# a term that holds, and one that does not
TRUE, FALSE = "true", "false"

# the least value each named term can take on the path, by its text
type Least = Mapping[str, int]


@dataclass(frozen=True)
class Lin:
    """An Int term as a number plus named terms, each times a number: ``n + 3``, ``n - s``.

    Two positions that differ by a number, or by named terms whose least values settle it,
    compare without the solver.
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

    def lowest(self, least: Least) -> int | None:
        """The least the term can be, when each named term it adds has a known least value and
        it takes none away."""
        if any(factor < 0 or term not in least for term, factor in self.atoms):
            return None
        return self.const + sum(factor * least[term] for term, factor in self.atoms)

    def highest(self, least: Least) -> int | None:
        """The most the term can be, when it only takes away named terms with known least
        values."""
        if any(factor > 0 or term not in least for term, factor in self.atoms):
            return None
        return self.const + sum(factor * least[term] for term, factor in self.atoms)


def _number(value: int) -> str:
    return f"(- {-value})" if value < 0 else str(value)


def _scaled(term: str, factor: int) -> str:
    return term if factor == 1 else f"(* {_number(factor)} {term})"


@dataclass
class Piece:
    """A list as cvc5 reads it: its length, and the kinds of the items it can hand out.

    ``kinds`` are the kinds of the items the input and the target put in it, as core counts
    them; ``every`` adds the kinds of items the solver may add.
    """

    length: Lin
    kinds: frozenset[str]
    every: frozenset[str]


# where a list the seed names holds an item of a kind: the guard at a position
type Guard = Callable[[Lin, str, Least], str]


@dataclass
class Stored(Piece):
    """An argument's list, or a list inside one: an array per kind, read at a position, and
    where each kind is."""

    arrays: Callable[[str], str] = field(default=lambda kind: kind)
    guard: Guard = field(default=lambda position, kind, least: TRUE)


@dataclass
class Shown(Piece):
    """A list display: each item's term, or None for an item the solver does not read, and its
    kind."""

    items: list[tuple[str | None, str]] = field(default_factory=list)


@dataclass
class Joined(Piece):
    """Lists joined by `+`, in order."""

    parts: list[Piece] = field(default_factory=list)
    _flat: list[Piece] | None = None

    def flat(self) -> list[Piece]:
        """The parts with every join inside run flat, in order, worked out once.

        A list appended to in a loop is a join thousands deep; flat, a read runs along it as
        one row of parts, on a stack of its own.
        """
        if self._flat is None:
            flat: list[Piece] = []
            stack: list[Piece] = list(reversed(self.parts))
            while stack:
                part = stack.pop()
                if isinstance(part, Joined):
                    stack.extend(reversed(part.parts if part._flat is None else part._flat))
                else:
                    flat.append(part)
            self._flat = flat
        return self._flat


@dataclass
class Window(Piece):
    """A slice of a list: its position ``q`` reads the list at ``start + q``, or ``start - q``
    for a step of -1."""

    base: Piece = field(default_factory=lambda: Shown(Lin(), frozenset(), frozenset()))
    start: Lin = field(default_factory=Lin)
    step: int = 1


@dataclass
class Repeated(Piece):
    """A list repeated a plain number of times: its position ``q`` reads the list at
    ``q mod len``, so a repeat costs one piece however many times it repeats."""

    base: Piece = field(default_factory=lambda: Shown(Lin(), frozenset(), frozenset()))


@dataclass(frozen=True)
class Read:
    """What reading one position gives: the item's term, or None where no item of the kind
    read can be, and when the item there is of that kind."""

    value: str | None
    guard: str


def compare(low: Lin, high: Lin, least: Least, *, or_equal: bool = False) -> str:
    """``low < high``, or ``low <= high``, decided here when the difference says."""
    difference = high.minus(low)
    lowest = difference.lowest(least)
    highest = difference.highest(least)
    if lowest is not None and (lowest > 0 or (or_equal and lowest >= 0)):
        return TRUE
    if highest is not None and (highest < 0 or (not or_equal and highest <= 0)):
        return FALSE
    op = "<=" if or_equal else "<"
    return f"({op} {low.text()} {high.text()})"


def equal(position: Lin, at: int, least: Least) -> str:
    """``position == at``, decided here when the difference says."""
    below = compare(position, Lin(at), least)
    above = compare(Lin(at), position, least)
    if FALSE == below == above:
        return TRUE
    if TRUE in (below, above):
        return FALSE
    return f"(= {position.text()} {at})"


def ite(condition: str, then: str, otherwise: str) -> str:
    if condition == TRUE or then == otherwise:
        return then
    if condition == FALSE:
        return otherwise
    return f"(ite {condition} {then} {otherwise})"


def nested(branches: Iterable[tuple[str, str]], last: str) -> str:
    """``(ite c1 v1 (ite c2 v2 ... last))``, each branch taken when its condition holds first.

    Written in one join, so a read through thousands of pieces costs their length, not its
    square. A branch whose condition fails is left out, and one that holds ends the chain.
    """
    kept: list[str] = []
    for condition, value in branches:
        if condition == FALSE:
            continue
        if condition == TRUE:
            last = value
            break
        kept.append(f"(ite {condition} {value} ")
    return "".join(kept) + last + ")" * len(kept)


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


def shape_guard(shape: ListShape) -> Guard:
    """Where a list of the input holds an item of a kind: the runs of the input that hold it,
    and past the input when an added item is of it."""
    runs = shape.runs()

    def guard(position: Lin, kind: str, least: Least) -> str:
        found = FALSE
        for run_kind, start, stop in runs:
            if run_kind == kind:
                within = both(
                    compare(Lin(start), position, least, or_equal=True),
                    compare(position, Lin(stop), least),
                )
                found = either(found, within)
        if shape.fill == kind:
            added = compare(Lin(len(shape.kinds)), position, least, or_equal=True)
            found = either(found, added)
        return found

    return guard

"""An item of a tracked list read at a position, split at the pieces the position can land in.

A read walks the tree of pieces a list was built from with ``ite``, one branch per piece the
position can reach, so the program holds no store and no sequence: after 3,000 appends,
``out[3]`` reaches five pieces and ``out[-1]`` one. A list changed in place names the list
before it more than once, `items[:i] + [x] + items[i:][1:]` say, so the same piece is read at
the same position along many paths: each is written once and named again, which keeps a read
through a long run of changes as long as the run. The walk runs on a stack of its own, and it
stops at the solve's deadline, so the time a program takes to write is part of the time limit.

Every item keeps its kind, so a read of an int is a read of the int array, and when the list
also holds items of other kinds the read carries a guard: where the position lands, the item is
of the kind the target read.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from pyct.solver.list_terms import (
    FALSE,
    TRUE,
    Counted,
    Counts,
    Joined,
    Least,
    Lin,
    Piece,
    Read,
    Repeated,
    Shown,
    Stored,
    Window,
    compare,
    equal,
    nested,
)

# how many steps a read takes between two looks at the clock
_STEPS_PER_LOOK = 64

# a read already written, by the piece, the position's text and the kind read
type Memo = dict[tuple[int, str, str], Read]


@dataclass(frozen=True)
class _Join:
    """The branches of one read, to put together once each is read: the read's key in the memo,
    and the condition of each branch but the last."""

    key: tuple[int, str, str]
    conditions: list[str]


# one step of a read: a piece to read at a position, or the branches of a read to put together
type _Task = tuple[Piece, Lin] | _Join


class RenderTimeError(Exception):
    """Writing the program ran past the solve's deadline."""


class RenderTooLargeError(Exception):
    """A read ran past its steps: it goes through a list cut at clamps the path leaves open.

    ``passed`` holds the list parts the read went through, by their place in the order they
    were built: the ones whose clamps a writing that settles them should settle.
    """

    def __init__(self, message: str, passed: frozenset[int] = frozenset()) -> None:
        super().__init__(message)
        self.passed = passed


class ProgramTooLargeError(Exception):
    """The reads of one program ran past the steps they share: a list cut again and again at
    clamps no writing settles, read through every cut."""


@dataclass
class Shared:
    """The steps every read of one program may still take together."""

    left: int

    def spend(self, steps: int) -> None:
        self.left -= steps
        if self.left < 0:
            raise ProgramTooLargeError("the reads ran past the steps the program gives them")


# a term written once in the program, by its text and its sort, and the name it goes by
type Define = Callable[[str, str], str]

# a read longer than this is written once, as a definition, and named wherever it is read again
_LONGEST_WRITTEN = 64


@dataclass(frozen=True)
class Context:
    """What every read of one program shares: each named term's least value on the path, the
    reads already written, how a term is defined once, the sort of each kind read, and the
    monotonic instant writing must end by."""

    least: Least
    memo: Memo
    define: Define
    sorts: Mapping[str, str]
    until: float | None
    # the steps one read may take, None for no limit, and the pieces a read went through
    steps: int | None = None
    visited: set[int] = field(default_factory=set)
    # the steps every read of the program may still take together, None for no limit
    shared: Shared | None = None
    # each split's count, which a compare with a number writes as whether a piece is there
    counts: Counts = field(default_factory=dict)


def read(piece: Piece, position: Lin, kind: str, context: Context) -> Read:
    """The item of ``kind`` at ``position``."""
    found = _Reader(kind, context).read(piece, position)
    # a list whose every item is of the kind read needs no guard: the path keeps the position
    # inside the list, and any item there is of that kind. A split's piece, read from its list
    # or one built from it, keeps the condition that it is there, which render asserts for each
    # piece a fork reads: through a slice, a read at a count dropped it, and an answer held the
    # piece at a line its string did not have
    if piece.every <= {kind} and not piece.of_a_split:
        return Read(found.value, TRUE)
    return found


class _Reader:
    """One read, its pieces walked on a stack of its own and put together as they finish."""

    def __init__(self, kind: str, context: Context) -> None:
        self.kind = kind
        self.least = context.least
        self.memo = context.memo
        self.until = context.until
        self.context = context

    def _kept(self, key: tuple[int, str, str], found: Read) -> Read:
        """A read, kept for the next time the same piece is read at the same position. A long
        one is defined once and named, so a list changed in place, which names the list before
        it more than once, is written once however many paths reach it."""
        value, guard = found.value, found.guard
        if value is not None and len(value) > _LONGEST_WRITTEN:
            value = self.context.define(value, self.context.sorts[self.kind])
        if len(guard) > _LONGEST_WRITTEN:
            guard = self.context.define(guard, "Bool")
        self.memo[key] = Read(value, guard)
        return self.memo[key]

    def read(self, piece: Piece, position: Lin) -> Read:
        tasks: list[_Task] = [(piece, position)]
        done: list[Read] = []
        steps = 0
        while tasks:
            steps += 1
            if steps % _STEPS_PER_LOOK == 0:
                self._in_time()
                self._in_steps(steps)
            task = tasks.pop()
            if isinstance(task, _Join):
                self._put_together(task, done)
            else:
                self._step(task[0], task[1], tasks, done)
        if self.context.shared is not None:
            self.context.shared.spend(steps % _STEPS_PER_LOOK)
        return done[0]

    def _in_steps(self, steps: int) -> None:
        most = self.context.steps
        if most is not None and steps > most:
            raise RenderTooLargeError("a read ran past its steps")
        if self.context.shared is not None:
            self.context.shared.spend(_STEPS_PER_LOOK)

    def _in_time(self) -> None:
        if self.until is not None and time.monotonic() > self.until:
            raise RenderTimeError("writing the program ran past the solve's time limit")

    def _step(self, piece: Piece, position: Lin, tasks: list[_Task], done: list[Read]) -> None:
        """One piece at one position: a read already written, one that ends here, or the
        pieces it goes on into, put together once they are read."""
        key = (id(piece), position.text(), self.kind)
        self.context.visited.add(id(piece))
        if key in self.memo:
            done.append(self.memo[key])
            return
        branches = self._branches(piece, position)
        if isinstance(branches, Read):
            done.append(self._kept(key, branches))
            return
        conditions, parts = branches
        tasks.append(_Join(key, conditions))
        tasks.extend(reversed(parts))

    def _put_together(self, join: _Join, done: list[Read]) -> None:
        count = len(join.conditions) + 1
        parts = done[-count:]
        del done[-count:]
        done.append(self._kept(join.key, chosen(join.conditions, parts)))

    def _branches(
        self, piece: Piece, position: Lin
    ) -> Read | tuple[list[str], list[tuple[Piece, Lin]]]:
        """A read that ends at this piece, or the pieces it goes on into and when each."""
        if isinstance(piece, Stored):
            return self._stored(piece, position)
        if isinstance(piece, Shown):
            return self._shown(piece, position)
        if isinstance(piece, Window):
            return [], [(piece.base, piece.start.plus(position, piece.step))]
        if isinstance(piece, Repeated):
            return [], [(piece.base, _wrapped(position, piece.base.length))]
        if isinstance(piece, Counted):
            return piece.at(position, self.kind, self.least)
        assert isinstance(piece, Joined)
        return self._joined(piece, position)

    def _stored(self, piece: Stored, position: Lin) -> Read:
        if self.kind not in piece.every:
            return Read(None, FALSE)
        guard = piece.guard(position, self.kind, self.least)
        return Read(f"(select {piece.arrays(self.kind)} {position.text()})", guard)

    def _shown(self, piece: Shown, position: Lin) -> Read:
        """A display: the item the position is, each one a branch."""
        values: list[tuple[str, str]] = []
        places: list[str] = []
        for at, (term, item_kind) in enumerate(piece.items):
            here = equal(position, at, self.least)
            if here == FALSE or term is None or item_kind != self.kind:
                continue
            values.append((here, term))
            places.append(here)
        if not values:
            return Read(None, FALSE)
        value = nested(values[:-1], values[-1][1])
        every = all(term is not None and kind == self.kind for term, kind in piece.items)
        return Read(value, TRUE if every or TRUE in places else _any(places))

    def _joined(
        self, piece: Joined, position: Lin
    ) -> Read | tuple[list[str], list[tuple[Piece, Lin]]]:
        """Joined lists: the part the position lands in, each part a branch taken when the
        position is before its end, those it cannot reach left out."""
        conditions: list[str] = []
        parts: list[tuple[Piece, Lin]] = []
        offset = Lin()
        for part in piece.flat():
            end = offset.plus(part.length)
            before_end = compare(position, end, self.least, counts=self.context.counts)
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


def _wrapped(position: Lin, length: Lin) -> Lin:
    """A position of a list repeated, as a position of the list: ``q mod len``, worked out
    here when both are numbers. A read of the repeat is inside it, so the length is above 0
    and the position not negative, where SMT-LIB's `mod` is Python's `%`."""
    at, size = position.number(), length.number()
    if at is not None and size is not None and size > 0:
        return Lin(at % size)
    return Lin.of(f"(mod {position.text()} {length.text()})")


def _any(places: list[str]) -> str:
    return places[0] if len(places) == 1 else f"(or {' '.join(places)})"


def chosen(conditions: list[str], parts: list[Read]) -> Read:
    """Branches put together: the first part whose condition holds, the last one else.

    A branch where no item of the kind read can be is left out of the value and turns its
    guard false, so the solver keeps the position away from it.
    """
    branches = list(zip(conditions, parts[:-1], strict=True))
    values = [
        (condition, value) for condition, part in branches if (value := part.value) is not None
    ]
    last = parts[-1].value
    if last is None and values:
        last = values.pop()[1]
    guards = [(c, part.guard if part.value is not None else FALSE) for c, part in branches]
    last_guard = parts[-1].guard if parts[-1].value is not None else FALSE
    if all(guard == last_guard for _, guard in guards):
        guard = last_guard
    else:
        guard = nested(guards, last_guard)
    return Read(None if last is None else nested(values, last), guard)

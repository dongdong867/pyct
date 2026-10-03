"""One input's facts read back from its journal, while its process runs and once it has ended.

pyct's process reads the records the input's process commits as the
process goes, a look every so often while it waits (see ``process``), and
the rest once the process has ended. So an input that records many facts
before its deadline leaves little to read after it: reading them all after
the deadline took about 0.65 s for 100,000 forks, where the run must end
within a second of its deadline.

A look reads only the records committed by the look before it, not those
committed since. The writer's bytes go first and its committed mark after,
but another processor may see the two stores in the other order, and only
the end of the process orders them for certain; a mark some milliseconds
old has long had its bytes arrive. The last downgrade entry's count can
still grow in place, so the reading after the process ended reads it again.

A look that meets a record it cannot read stops looking. The reading after
the process ended reads that record again, and only then does the record
stop the reading, so every fact before it stays, as the journal's layout
says (see ``journal``).
"""

from __future__ import annotations

import json
import struct
from collections.abc import Buffer
from dataclasses import dataclass, field

from pyct.core.branch import Branch, Expression, Fact, Site
from pyct.results.failure import Failure, FailureKind
from pyct.results.record import DowngradeCount
from pyct.run.journal import (
    CARRY_ON,
    COMMITTED,
    COUNTED,
    DOWNGRADE,
    END,
    FACT,
    FORK,
    FULL,
    HEAD,
    LINE,
    NOTE_AT,
    NOTE_SIZE,
    NUMBER,
    OPEN,
    PART,
    RECORDS,
    START,
    STATE,
    UNENCODABLE,
    WORD,
    Journal,
    padded,
)

_DECODER = json.JSONDecoder()

# the most bytes of records one look starts reading, about 4 ms of reading where it was measured:
# a look that stops here says so, and the wait looks again at once, asking between the two
# whether the process ended or is due its kill
LOOK_BYTES = 256 * 1024

# the types of a leaf besides None: a name or literal, a number, a truth value
_LEAVES = (str, int, float)


class _UnreadableError(Exception):
    """A record the reader cannot read. It carries the byte the record starts at."""

    def __init__(self, at: int) -> None:
        super().__init__(at)
        self.at = at


@dataclass(frozen=True)
class Reading:
    """What one input's journal held: its facts, its own ending, and why it may be incomplete.

    ``started`` says pyct's side of the input's process came up. ``ended``
    says the call finished and wrote ``end``, which is its failure or None.
    ``problem`` says the facts are known to be incomplete: the writer
    stopped, or a record could not be read.
    """

    lines: frozenset[int]
    branches: tuple[Branch, ...]
    downgrades: tuple[DowngradeCount, ...]
    started: bool = False
    ended: bool = False
    end: Failure | None = None
    problem: str | None = None
    facts: tuple[Fact, ...] = ()


def read(buffer: Journal) -> Reading:
    """Every fact the journal committed, in the order the call made them, read at once."""
    return JournalReader(buffer).finish()


class JournalReader:
    """Reads one journal: a look at a time while its writer runs, the rest once it has ended."""

    def __init__(self, buffer: Journal) -> None:
        self._buffer = buffer
        self._facts = _Facts()
        # where the next record starts, and the committed mark the last look saw
        self._at = RECORDS
        self._seen = RECORDS
        self._looking = True

    def look(self) -> bool:
        """Read the records the last look saw committed, those that start within ``LOOK_BYTES``.

        The writer may still be writing. Whether the look stopped at its
        bound with more of them left, so the next look need not wait.
        """
        if not self._looking:
            return False
        end = self._seen
        with memoryview(self._buffer) as view:
            (mark,) = WORD.unpack_from(view, COMMITTED * WORD.size)
            try:
                self._at = self._facts.take_all(view, self._at, end, self._at + LOOK_BYTES)
            except _UnreadableError as error:
                # the records before it are taken; the end reads on from this one
                self._at = error.at
                self._looking = False
            if RECORDS <= mark <= len(view):
                self._seen = max(self._seen, mark)
        return self._looking and self._at < end

    def finish(self) -> Reading:
        """Every fact the journal committed, once its writer's process has ended.

        A state or a committed mark it cannot read keeps no fact, as a
        record it cannot read keeps those before it.
        """
        problem = None
        with memoryview(self._buffer) as view:
            try:
                problem = _noted(view)
                end = _committed(view)
            except _UnreadableError as error:
                return _Facts().reading(problem or _unreadable(error.at))
            try:
                self._at = self._facts.take_all(view, self._at, end)
            except _UnreadableError as error:
                problem = problem or _unreadable(error.at)
            self._facts.recount(view)
        return self._facts.reading(problem)


def _unreadable(at: int) -> str:
    return f"could not read the input's facts at byte {at}"


def _noted(view: memoryview) -> str | None:
    """Why the writer stopped, or None while it was still writing."""
    (word,) = WORD.unpack_from(view, STATE * WORD.size)
    state, length = word & 0xFFFF, word >> 16
    if state == OPEN:
        return None
    if state not in (FULL, UNENCODABLE):
        raise _UnreadableError(STATE * WORD.size)
    return bytes(view[NOTE_AT : NOTE_AT + min(length, NOTE_SIZE)]).decode("utf-8", "replace")


def _committed(view: memoryview) -> int:
    """Where the committed records end. A journal no record was committed to ends at its start."""
    (committed,) = WORD.unpack_from(view, COMMITTED * WORD.size)
    if committed == 0:
        return RECORDS
    if not RECORDS <= committed <= len(view):
        raise _UnreadableError(0)
    return committed


@dataclass
class _Facts:
    """The facts read so far, and every part, by number, as the one list each stands for.

    Each site is one ``Site`` however many forks name it, so a long path
    holds its file's name once.
    """

    lines: set[int] = field(default_factory=set)
    branches: list[Branch] = field(default_factory=list)
    # the facts the path holds, each placed after the fork records read before it
    facts: list[Fact] = field(default_factory=list)
    downgrades: list[DowngradeCount] = field(default_factory=list)
    parts: dict[int, list[Expression]] = field(default_factory=dict)
    sites: dict[tuple[str, int, int], Site] = field(default_factory=dict)
    started: bool = False
    ended: bool = False
    end: Failure | None = None
    # where the last downgrade record starts, whose count may have grown since it was read
    counted_at: int | None = None

    def take_all(self, view: memoryview, at: int, end: int, stop: int | None = None) -> int:
        """Add each record from ``at`` up to ``end``, and return where the next one starts.

        With ``stop``, only the records that start before it.
        """
        stop = end if stop is None else min(stop, end)
        while at < stop:
            if at + HEAD.size > end:
                raise _UnreadableError(at)
            length, kind = HEAD.unpack_from(view, at)
            start = at + HEAD.size
            if start + length > end:
                raise _UnreadableError(at)
            payload = view[start : start + length]
            try:
                self._take(at, kind, payload)
            except (ValueError, TypeError, struct.error) as error:
                raise _UnreadableError(at) from error
            finally:
                # a stop raised meanwhile keeps this frame, and a live slice would keep the
                # journal from being unmapped
                payload.release()
            at = start + padded(length)
        return at

    def _take(self, at: int, kind: int, payload: memoryview) -> None:
        """Add one record's fact. A record of an unknown kind or the wrong shape is unreadable."""
        if kind in (PART, FORK, FACT):
            self._written(kind, _decoded(payload))
        elif kind == LINE:
            self.lines.add(NUMBER.unpack(payload)[0])
        elif kind in (DOWNGRADE, CARRY_ON):
            # the entry before stopped growing when the writer began this one
            self.recount(payload.obj)
            self._downgrade(bytes(payload), carries_on=kind == CARRY_ON)
            self.counted_at = at
        elif kind == START:
            self.started = True
        elif kind == END:
            ending = _ending(_decoded(payload))
            self.ended, self.end = True, ending
        else:
            raise ValueError(f"no record of kind {kind}")

    def _written(self, kind: int, value: object) -> None:
        """Add a record written as JSON: a part, a fork or a fact."""
        if kind == PART:
            number, items = _numbered(value)
            self.parts[number] = [self._expression(item) for item in items]
        elif kind == FORK:
            self.branches.append(self._fork(value))
        else:
            self.facts.append(self._fact(value))

    def _downgrade(self, payload: bytes, *, carries_on: bool) -> None:
        """Start an entry, or carry the last one on when this record is its later count.

        Only the writer knows a count carries an entry on, so it says so by the
        record's kind. A new entry after a lost one of another name is a plain
        downgrade record, and stays its own however far it grows.
        """
        count, line, col = COUNTED.unpack_from(payload)
        name, file = payload[COUNTED.size :].decode(errors="surrogatepass").split("\0")
        entry = DowngradeCount(name, count, Site(file=file, line=line, col=col))
        last = self.downgrades[-1] if self.downgrades else None
        if carries_on and last is not None and (last.name, last.site) == (name, entry.site):
            self.downgrades[-1] = entry
        else:
            self.downgrades.append(entry)

    def recount(self, view: Buffer) -> None:
        """Read the last entry's count again: the writer grows it in place while it repeats, so
        a look can have read it short."""
        if self.counted_at is None:
            return
        (count,) = WORD.unpack_from(view, self.counted_at + HEAD.size)
        last = self.downgrades[-1]
        self.downgrades[-1] = DowngradeCount(last.name, count, last.site)

    def _fork(self, value: object) -> Branch:
        match value:
            case [
                expression,
                bool() as taken,
                str() as file,
                int() as line,
                int() as col,
                bool() as raising,
            ]:
                site = self._site(file, line, col)
                return Branch(self._expression(expression), taken, site, raising=raising)
        raise ValueError("a fork is [expression, taken, file, line, col, raising]")

    def _fact(self, value: object) -> Fact:
        """A fact, placed after every fork record read before it."""
        match value:
            case [
                expression,
                bool() as taken,
                str() as file,
                int() as line,
                int() as col,
                bool() as raising,
                *place,
            ] if len(place) <= 1:
                site = self._site(file, line, col)
                held = self._expression(place[0]) if place else None
                fact = Fact(self._expression(expression), taken, site, raising, held)
                return fact.placed_after(len(self.branches))
        raise ValueError("a fact is [expression, taken, file, line, col, raising] and its place")

    def _site(self, file: str, line: int, col: int) -> Site:
        """The one ``Site`` for this place, made the first time a fork names it."""
        key = (file, line, col)
        site = self.sites.get(key)
        if site is None:
            site = self.sites[key] = Site(file=file, line=line, col=col)
        return site

    def _expression(self, value: object) -> Expression:
        """A leaf, or the one list a part number stands for, shared wherever it is named."""
        if value is None or isinstance(value, _LEAVES):
            return value
        match value:
            case [int() as number] if not isinstance(number, bool) and number in self.parts:
                return self.parts[number]
        raise ValueError("an expression holds leaves and parts already read")

    def reading(self, problem: str | None) -> Reading:
        return Reading(
            lines=frozenset(self.lines),
            branches=tuple(self.branches),
            downgrades=tuple(self.downgrades),
            facts=tuple(self.facts),
            started=self.started,
            ended=self.ended,
            end=self.end,
            problem=problem,
        )


def _decoded(payload: memoryview) -> object:
    """A record's JSON, which the writer wrote as ASCII, read as ``json.loads`` reads its bytes."""
    return _DECODER.decode(str(payload, "utf-8", "surrogatepass"))


def _numbered(value: object) -> tuple[int, list[object]]:
    """A part as written: its number, and its items, head first."""
    match value:
        case [int() as number, head, *rest] if not isinstance(number, bool):
            return number, [head, *rest]
    raise ValueError("a part is [number, head, ...]")


def _ending(value: object) -> Failure | None:
    """The call's own ending: None when it returned, else its failure."""
    match value:
        case None:
            return None
        case [str() as kind, str() as detail, str() | None as traceback]:
            return Failure(kind=FailureKind(kind), detail=detail, traceback=traceback)
    raise ValueError("an ending is null or [kind, detail, traceback]")

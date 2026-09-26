"""One input's facts on their way out of the input's process, in shared memory.

The input's process writes each fact the moment the call makes it, and
pyct's process reads them all once that process has ended, however it
ended: a crash or a kill keeps every fact already written. Shared memory
rather than a pipe, because a write costs a store and not a system call
(0.05 to 0.33 µs a fact against 0.6 to 0.75 µs), a downgrade loop repeats
one fact millions of times, and pyct's process only waits instead of
reading as it goes.

The layout. A header of two words, each a native u64 since both
processes run on one machine: the committed mark, where the complete
records end, and the state, open, full, or unencodable, with its note's
length above bit 16; then a 1 KiB note saying why the writer stopped.
Then records, each an 8-byte little-endian head (u32 payload length, u8
kind) and its payload, padded to 8 bytes:

- line: an i64, the first time the call reaches that line.
- part: one list of an expression, as JSON. A leaf is a JSON scalar and a
  list inside it is ``[n]``, the part written n-th. An expression is a
  graph in which one list can sit in many places, and a loop that doubles
  a value doubles the expression written out on every pass, so each list
  is written once, however many places hold it, and read back as one list
  in all of them.
- fork: JSON ``[expression, taken, file, line, col]``, the expression a
  leaf or ``[n]``.
- downgrade: a native u64 count, then the name. A repeat of the last
  entry rewrites its count in place.
- end: JSON ``null`` for a call that returned, else ``[kind, detail,
  traceback]``.

A record's bytes go first and the committed mark moves past them after, so
the journal holds a readable prefix at every instant. Every word the
reader trusts, the mark, the state and a count, changes in one aligned
8-byte store through a word view of the journal, so a kill never finds it
half written. ``struct.pack_into`` would not do: it clears its bytes
before it writes them. JSON decodes to
lists and scalars only, never to an object whose code runs, which matters
because the writer ran the target's code in its own process; and it
writes an int subclass by int's own repr, so no target code runs on the
way out either.

A journal past ``CAPACITY``, or a fact the writer cannot encode, stops the
writer: it notes why and writes nothing more. A record the reader cannot
read stops the reading at its byte. Either way the facts before it stay,
and the input's line says pyct failed, since its facts are known to be
incomplete.
"""

from __future__ import annotations

import json
import mmap
import struct
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import TypeGuard

from pyct.core.branch import Branch, Expression, Site
from pyct.results.failure import Failure, FailureKind
from pyct.results.record import DowngradeCount

# the most bytes one input's journal holds. Mapped lazily: an input pays for what it writes
CAPACITY = 256 * 1024 * 1024

type Journal = mmap.mmap | bytearray

# the header's words, by index into the journal's native u64 view
_COMMITTED, _STATE = 0, 1
_WORD = struct.Struct("=Q")
_NOTE_AT = 16
_NOTE_SIZE = 1024
# where the first record starts, after the header
RECORDS = _NOTE_AT + _NOTE_SIZE

_HEAD = struct.Struct("<IB3x")
_NUMBER = struct.Struct("<q")

_LINE, _PART, _FORK, _DOWNGRADE, _END = 1, 2, 3, 4, 5
_OPEN, _FULL, _UNENCODABLE = 0, 1, 2


class _UnencodableError(Exception):
    """A fact the journal has no encoding for. The writer stops on it."""


class JournalWriter:
    """Writes one input's facts into its journal as they happen. It is the call's ``Watch``.

    It never raises into the target: a fact it cannot keep stops it, with a
    note the reader turns into the input's failure.
    """

    def __init__(self, buffer: Journal) -> None:
        self._buffer = buffer
        self._words = memoryview(buffer)[: len(buffer) // _WORD.size * _WORD.size].cast("Q")
        self._at = RECORDS
        self._open = True
        self._count_at: int | None = None
        # each list already written, by identity, with the list itself so its id stays its own
        self._parts: dict[int, tuple[int, list[Expression]]] = {}

    def fork(self, branch: Branch) -> None:
        """Write a fork the call took, and every part of its expression not written yet."""
        try:
            expression = self._written(branch.expression)
        except _UnencodableError as error:
            self._stop(_UNENCODABLE, f"could not keep a fork the input took: {error}")
            return
        site = branch.site
        self._json(_FORK, [expression, branch.taken, site.file, site.line, site.col])

    def line(self, number: int) -> None:
        """Write a line the call reached for the first time."""
        self._record(_LINE, _NUMBER.pack(number))

    def downgrade(self, name: str, count: int) -> None:
        """Write a new downgrade entry at a count of 1, or grow the last one in place."""
        if count > 1 and self._count_at is not None:
            if self._open:
                self._words[self._count_at // _WORD.size] = count
            return
        at = self._at
        if self._record(_DOWNGRADE, _WORD.pack(count) + name.encode()):
            self._count_at = at + _HEAD.size

    def end(self, failure: Failure | None) -> None:
        """Write how the call ended. The reader takes it as the input's own ending."""
        if failure is None:
            self._json(_END, None)
            return
        self._json(_END, [failure.kind.value, failure.detail, failure.traceback])

    def detach(self) -> None:
        """Write nothing more. A process the input's process forks calls this in its child."""
        self._open = False

    def _written(self, expression: Expression) -> object:
        """The expression as a fork holds it: a leaf, or ``[n]`` once its parts are written.

        Children first, from an explicit stack, because a deep expression would
        pass Python's recursion limit, which the target may also have lowered.
        """
        if not isinstance(expression, list):
            return _leaf(expression)
        stack: list[tuple[list[Expression], bool]] = [(expression, False)]
        opened: set[int] = set()
        while stack and self._open:
            part, children_written = stack.pop()
            if id(part) in self._parts:
                continue
            if children_written:
                self._part(part)
                continue
            if id(part) in opened:
                raise _UnencodableError("it holds itself")
            opened.add(id(part))
            stack.append((part, True))
            stack.extend((child, False) for child in part if isinstance(child, list))
        return [self._parts[id(expression)][0]] if id(expression) in self._parts else None

    def _part(self, part: list[Expression]) -> None:
        """Write one list whose inner lists are all written, and remember its number."""
        payload = [
            [self._parts[id(child)][0]] if isinstance(child, list) else _leaf(child)
            for child in part
        ]
        if self._json(_PART, payload):
            self._parts[id(part)] = (len(self._parts), part)

    def _json(self, kind: int, value: object) -> bool:
        return self._record(kind, json.dumps(value).encode())

    def _record(self, kind: int, payload: bytes) -> bool:
        """Write one record and commit it. False when the writer is stopped or it does not fit."""
        if not self._open:
            return False
        at = self._at
        after = at + _HEAD.size + _padded(len(payload))
        if after > len(self._buffer):
            self._stop(_FULL, f"the journal is full at {len(self._buffer)} bytes")
            return False
        _HEAD.pack_into(self._buffer, at, len(payload), kind)
        self._buffer[at + _HEAD.size : at + _HEAD.size + len(payload)] = payload
        self._at = after
        self._words[_COMMITTED] = after
        return True

    def _stop(self, state: int, note: str) -> None:
        """Note why nothing more is written, and write nothing more."""
        if not self._open:
            return
        noted = note.encode("utf-8", "replace")[:_NOTE_SIZE]
        self._buffer[_NOTE_AT : _NOTE_AT + len(noted)] = noted
        self._words[_STATE] = state | len(noted) << 16
        self._open = False


def _leaf(value: object) -> object:
    """A leaf as JSON holds it. A kind no expression holds cannot be written."""
    if not _is_leaf(value):
        raise _UnencodableError(f"a leaf of type {type(value).__name__}")
    return value


def _is_leaf(value: object) -> TypeGuard[Expression]:
    """A name or literal, a number, a truth value, or null: every leaf an expression holds."""
    return value is None or isinstance(value, str | int)


def _padded(length: int) -> int:
    return -(-length // 8) * 8


class _UnreadableError(Exception):
    """A record the reader cannot read. It carries the byte the record starts at."""

    def __init__(self, at: int) -> None:
        super().__init__(at)
        self.at = at


@dataclass(frozen=True)
class Reading:
    """What one input's journal held: its facts, its own ending, and why it may be incomplete.

    ``ended`` says the call finished and wrote ``end``, which is its failure
    or None. ``problem`` says the facts are known to be incomplete: the
    writer stopped, or a record could not be read.
    """

    lines: frozenset[int]
    branches: tuple[Branch, ...]
    downgrades: tuple[DowngradeCount, ...]
    ended: bool = False
    end: Failure | None = None
    problem: str | None = None


def read(buffer: Journal) -> Reading:
    """Every fact the journal committed, in the order the call made them."""
    facts = _Facts()
    problem = None
    with memoryview(buffer) as view:
        try:
            problem = _noted(view)
            for at, kind, payload in _records(view):
                facts.take(at, kind, payload)
        except _UnreadableError as error:
            problem = problem or f"could not read the input's facts at byte {error.at}"
    return facts.reading(problem)


def _noted(view: memoryview) -> str | None:
    """Why the writer stopped, or None while it was still writing."""
    (word,) = _WORD.unpack_from(view, _STATE * _WORD.size)
    state, length = word & 0xFFFF, word >> 16
    if state == _OPEN:
        return None
    if state not in (_FULL, _UNENCODABLE):
        raise _UnreadableError(_STATE * _WORD.size)
    return bytes(view[_NOTE_AT : _NOTE_AT + min(length, _NOTE_SIZE)]).decode("utf-8", "replace")


def _records(view: memoryview) -> Iterator[tuple[int, int, bytes]]:
    """Each committed record: where it starts, its kind, and its payload."""
    (committed,) = _WORD.unpack_from(view, _COMMITTED * _WORD.size)
    if committed == 0:
        return
    if not RECORDS <= committed <= len(view):
        raise _UnreadableError(0)
    at = RECORDS
    while at < committed:
        if at + _HEAD.size > committed:
            raise _UnreadableError(at)
        length, kind = _HEAD.unpack_from(view, at)
        start = at + _HEAD.size
        if start + length > committed:
            raise _UnreadableError(at)
        yield at, kind, bytes(view[start : start + length])
        at = start + _padded(length)


@dataclass
class _Facts:
    """The facts read so far, and every part, by number, as the one list each stands for."""

    lines: set[int] = field(default_factory=set)
    branches: list[Branch] = field(default_factory=list)
    downgrades: list[DowngradeCount] = field(default_factory=list)
    parts: list[list[Expression]] = field(default_factory=list)
    ended: bool = False
    end: Failure | None = None

    def take(self, at: int, kind: int, payload: bytes) -> None:
        """Add one record's fact. A record of an unknown kind or the wrong shape is unreadable."""
        try:
            self._take(kind, payload)
        except (ValueError, TypeError, struct.error) as error:
            raise _UnreadableError(at) from error

    def _take(self, kind: int, payload: bytes) -> None:
        if kind == _LINE:
            self.lines.add(_NUMBER.unpack(payload)[0])
        elif kind == _PART:
            self.parts.append([self._expression(child) for child in _list(json.loads(payload))])
        elif kind == _FORK:
            self.branches.append(self._fork(json.loads(payload)))
        elif kind == _DOWNGRADE:
            (count,) = _WORD.unpack_from(payload)
            self.downgrades.append(DowngradeCount(payload[_WORD.size :].decode(), count))
        elif kind == _END:
            self.ended, self.end = True, _ending(json.loads(payload))
        else:
            raise ValueError(f"no record of kind {kind}")

    def _fork(self, value: object) -> Branch:
        match value:
            case [expression, bool() as taken, str() as file, int() as line, int() as col]:
                site = Site(file=file, line=line, col=col)
                return Branch(expression=self._expression(expression), taken=taken, site=site)
        raise ValueError("a fork is [expression, taken, file, line, col]")

    def _expression(self, value: object) -> Expression:
        """A leaf, or the one list a part number stands for, shared wherever it is named."""
        match value:
            case [int() as number] if not isinstance(number, bool) and 0 <= number < len(
                self.parts
            ):
                return self.parts[number]
        if isinstance(value, list) or not _is_leaf(value):
            raise ValueError("an expression holds leaves and parts already read")
        return value

    def reading(self, problem: str | None) -> Reading:
        return Reading(
            lines=frozenset(self.lines),
            branches=tuple(self.branches),
            downgrades=tuple(self.downgrades),
            ended=self.ended,
            end=self.end,
            problem=problem,
        )


def _list(value: object) -> list[object]:
    if not isinstance(value, list) or not value:
        raise ValueError("a part is a list with a head")
    return value


def _ending(value: object) -> Failure | None:
    """The call's own ending: None when it returned, else its failure."""
    match value:
        case None:
            return None
        case [str() as kind, str() as detail, str() | None as traceback]:
            return Failure(kind=FailureKind(kind), detail=detail, traceback=traceback)
    raise ValueError("an ending is null or [kind, detail, traceback]")

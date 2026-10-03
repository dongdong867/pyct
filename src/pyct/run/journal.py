"""One input's facts on their way out of the input's process, in shared memory.

The input's process writes each fact the moment the call makes it, and
pyct's process reads them back, as they are committed while that process
runs and the rest once it has ended, however it ended: a crash or a kill
keeps every fact already written (see ``journal_reader``). Shared memory
rather than a pipe, because a write costs a store and not a system call
(0.05 to 0.33 µs a fact against 0.6 to 0.75 µs), a downgrade loop repeats
one fact millions of times, and the input's process never waits for
pyct's to read.

The layout. A header of two words, each a native u64 since both
processes run on one machine: the committed mark, where the complete
records end, and the state, open, full, or unencodable, with its note's
length above bit 16; then a 1 KiB note saying why the writer stopped.
Then records, each an 8-byte little-endian head (u32 payload length, u8
kind) and its payload, padded to 8 bytes:

- start: no payload, written when pyct's side of the input's process is up,
  before the call begins. A journal without one belongs to a process that
  died before pyct's own code there ran.
- line: an i64, the first time the call reaches that line.
- part: one list of an expression, as JSON ``[n, head, ...]``: its number,
  then its items. A leaf is a JSON scalar and a list inside it is ``[n]``,
  the part numbered n. An expression is a graph in which one list can sit
  in many places, and a loop that doubles a value doubles the expression
  written out on every pass, so each list is written once, however many
  places hold it, and read back as one list in all of them.
- fork: JSON ``[expression, taken, file, line, col, raising]``, the
  expression a leaf or ``[n]``, and a seventh item, true, for a walk's fork
  over a split's list (``Branch.split_walk``).
- fact: a fact the path holds beside its forks (``Fact``), written as a fork
  is, its expression null for a fact that is only a place, and a seventh item
  for its place, written the same way. Its ``after`` is not written: the
  reader counts the fork records before it.
- downgrade: a native u64 count, the site's line and column as two i64,
  then the name and the site's file, a NUL between them. A repeat of the
  last entry rewrites its count in place.
- carry-on: the same, for a count past 1 the writer could not grow in place,
  because the alarm cut its note of the last entry short. The reader joins
  it to the entry before when that one has its name.
- end: JSON ``null`` for a call that returned, else ``[kind, detail,
  traceback]``.

A record's bytes go first and the committed mark moves past them after, so
the journal holds a readable prefix at every instant. Every word the
reader trusts, the mark, the state and a count, changes in one aligned
8-byte store through a word view of the journal, so a kill never finds it
half written. ``struct.pack_into`` would not do: it clears its bytes
before it writes them.

JSON decodes to lists and scalars only, never to an object whose code
runs, which matters because the writer ran the target's code in its own
process; and it writes an int subclass by int's own repr, so no target
code runs on the way out either.

The deadline's alarm can raise inside the writer, between any two lines,
and the writer goes on after it. So a part carries the number it was
given before it was written, and a count grows in place only on the entry
it was written for: whatever the writer's own notes lost, a later fact
still reads back as written.

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
from typing import TypeGuard

from pyct.core.branch import Branch, Expression, Fact, Site
from pyct.results.failure import Failure

# the most bytes one input's journal holds. Mapped lazily: an input pays for what it writes
CAPACITY = 256 * 1024 * 1024

type Journal = mmap.mmap | bytearray

# the header's words, by index into the journal's native u64 view
COMMITTED, STATE = 0, 1
WORD = struct.Struct("=Q")
NOTE_AT = 16
NOTE_SIZE = 1024
# where the first record starts, after the header
RECORDS = NOTE_AT + NOTE_SIZE

HEAD = struct.Struct("<IB3x")
NUMBER = struct.Struct("<q")
# a downgrade's count, then its site's line and column
COUNTED = struct.Struct("=Qqq")

LINE, PART, FORK, DOWNGRADE, END, START, CARRY_ON, FACT = 1, 2, 3, 4, 5, 6, 7, 8
OPEN, FULL, UNENCODABLE = 0, 1, 2


class _UnencodableError(Exception):
    """A fact the journal has no encoding for. The writer stops on it."""


class JournalWriter:
    """Writes one input's facts into its journal as they happen. It is the call's ``Watch``.

    It never raises into the target: a fact it cannot keep stops it, with a
    note the reader turns into the input's failure.
    """

    def __init__(self, buffer: Journal) -> None:
        self._buffer = buffer
        self._words = memoryview(buffer)[: len(buffer) // WORD.size * WORD.size].cast("Q")
        self._at = RECORDS
        self._open = True
        # where the last downgrade entry's count sits, and the name and site it counts
        self._count_at: int | None = None
        self._counting: tuple[str, Site] | None = None
        # each list already written, by identity, with the list itself so its id stays its own
        self._parts: dict[int, tuple[int, list[Expression]]] = {}
        self._next_part = 0

    def fork(self, branch: Branch) -> None:
        """Write a fork the call took, and every part of its expression not written yet."""
        site = branch.site
        try:
            expression = self._written(branch.expression)
            fork = [expression, branch.taken, site.file, site.line, site.col, branch.raising]
            if branch.split_walk:
                fork.append(True)
            self._json(FORK, fork)
        # ValueError: an int longer than Python writes out, under a limit the target may lower
        except (_UnencodableError, ValueError) as error:
            self._stop(UNENCODABLE, f"could not keep a fork the input took: {error}")

    def fact(self, fact: Fact) -> None:
        """Write a fact the path came to hold, and every part of it not written yet."""
        site = fact.site
        try:
            expression = self._written(fact.expression)
            held = [expression, fact.taken, site.file, site.line, site.col, fact.raising]
            if fact.place is not None:
                held.append(self._written(fact.place))
            self._json(FACT, held)
        except (_UnencodableError, ValueError) as error:
            self._stop(UNENCODABLE, f"could not keep a fact the input's path holds: {error}")

    def start(self) -> None:
        """Write that pyct's side of the input's process is up and the call is about to begin."""
        self._record(START, b"")

    def line(self, number: int) -> None:
        """Write a line the call reached for the first time."""
        self._record(LINE, NUMBER.pack(number))

    def downgrade(self, name: str, site: Site, count: int) -> None:
        """Grow the last entry in place when it counts ``name`` at ``site``, or write a new one."""
        if count > 1 and self._counting == (name, site) and self._count_at is not None:
            if self._open:
                self._words[self._count_at // WORD.size] = count
            return
        self._counting = None
        at = self._at
        kind = DOWNGRADE if count == 1 else CARRY_ON
        head = COUNTED.pack(count, site.line, site.col)
        if self._record(kind, head + f"{name}\0{site.file}".encode(errors="surrogatepass")):
            self._count_at = at + HEAD.size
            self._counting = (name, site)

    def end(self, failure: Failure | None) -> None:
        """Write how the call ended. The reader takes it as the input's own ending."""
        if failure is None:
            self._json(END, None)
            return
        self._json(END, [failure.kind.value, failure.detail, failure.traceback])

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
        """Write one list whose inner lists are all written, under a number of its own."""
        items = [
            [self._parts[id(child)][0]] if isinstance(child, list) else _leaf(child)
            for child in part
        ]
        number = self._next_part
        self._next_part = number + 1
        if self._json(PART, [number, *items]):
            self._parts[id(part)] = (number, part)

    def _json(self, kind: int, value: object) -> bool:
        return self._record(kind, json.dumps(value).encode())

    def _record(self, kind: int, payload: bytes) -> bool:
        """Write one record and commit it. False when the writer is stopped or it does not fit."""
        if not self._open:
            return False
        at = self._at
        after = at + HEAD.size + padded(len(payload))
        if after > len(self._buffer):
            self._stop(FULL, f"the journal is full at {len(self._buffer)} bytes")
            return False
        HEAD.pack_into(self._buffer, at, len(payload), kind)
        self._buffer[at + HEAD.size : at + HEAD.size + len(payload)] = payload
        self._at = after
        self._words[COMMITTED] = after
        return True

    def _stop(self, state: int, note: str) -> None:
        """Note why nothing more is written, and write nothing more."""
        if not self._open:
            return
        noted = note.encode("utf-8", "replace")[:NOTE_SIZE]
        self._buffer[NOTE_AT : NOTE_AT + len(noted)] = noted
        self._words[STATE] = state | len(noted) << 16
        self._open = False


def _leaf(value: object) -> object:
    """A leaf as JSON holds it. A kind no expression holds cannot be written."""
    if not _is_leaf(value):
        raise _UnencodableError(f"a leaf of type {type(value).__name__}")
    return value


def _is_leaf(value: object) -> TypeGuard[Expression]:
    """A name or literal, a number, a truth value, or null: every leaf an expression holds.

    A float crosses as the double it is: json writes NaN and the infinities
    as ``NaN`` and ``Infinity``, and -0.0 with its sign, and reads each back.
    """
    return value is None or isinstance(value, str | int | float)


def padded(length: int) -> int:
    return -(-length // 8) * 8

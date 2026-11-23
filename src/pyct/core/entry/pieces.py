"""The hooks around each piece of the target's functions, a loop or an assignment of a
comprehension (`pyct.results.pieces`), and the runs of each piece they record.

With the interception's pieces switch on, `pyct.intercept.loops` writes a
call of these functions where each piece starts and where it ends, through
a name it binds in the module, such as ``__pyct_piece_over__``. Each call
is given the piece's site and names as constants, in this order: its line,
its column, the names going in and the changed names, each a tuple of str.
The file is the one the caller's code names. Each hook is called from the
target's own frame, so ``sys._getframe(1)`` is the piece's frame, and each
hands back what the target's code needs.

While an input is live, from `start` to `forget`, the hooks record the
first `MOST_RUNS` runs of each piece, by its file, line and column, in that
input. The entry hook of one of those runs reads the piece's frame: each
name going in that is bound then, its value written as JSON text at that
moment, and whether the value was a tracked one. Its exit, `piece_out` in
the same frame for a loop or `piece_value` with the entry's token for an
assignment, reads each changed name bound then, an assignment's being the
value it is handed, and appends the run to the sink `start` was given, as
a `PieceRun`. A name is read from the frame by its written spelling, so one
Python stores under another spelling, a ``__name`` in a class body, is left
out of a run as an unbound one is. A run that ends by ``return`` or a raise
calls no exit and records nothing; the entry it left is dropped by the next
entry of that piece in that frame, and when the input ends. A run is recorded only when
each of its values is plain JSON data (`plain_json`) whose text is shorter
than `MOST_VALUE`, a tuple not being such data, and while it fits in what
the input's recorded runs may count together, `MOST_TEXT` by `size`. A
hook raises nothing of its own into the target, and reads each value
through its base type.

A hook that records nothing does little: with no input live it reads one
field, and past a piece's runs a lookup by its line, then one in the lines
the loops in use start at, which holds none while no loop is in use. A
piece that shares its line with another piece whose runs are all started
reads its frame on each entry instead, as would one given no names at all,
which `pyct.intercept.loops` leaves as written; an exit reads its frame
while an entry waits on its line. A piece at a line a loop in use starts at
enters `pyct.core.entry.in_use` on each entry.
"""

from __future__ import annotations

import contextlib
import sys
import types
from collections.abc import Callable, Mapping
from typing import cast

from pyct.core.entry import in_use
from pyct.core.entry.bases import TRACKED_CLASSES
from pyct.core.entry.in_use import USING, Run
from pyct.core.entry.waiting import Key, Waiting, json_text, popped
from pyct.core.foundation.branch import BranchSink, Changed, GoingIn, PieceRun, Site

# the runs of each piece recorded in an input, its first
MOST_RUNS = 3
# a recorded value's JSON text is shorter than this many characters, each one byte
MOST_VALUE = 2048
# what an input's recorded runs may count together, by `size`
MOST_TEXT = 1024 * 1024
# what `size` counts for each run, and for each value, beside their characters
RUN_COUNT, VALUE_COUNT = 64, 2

type _Site = tuple[str, int, int]


class _Entry:
    """A run's entry, waiting on its exit: its site, its values going in, its changed names, and
    where it waits. An assignment's entry hook hands it back as the token its exit gets."""

    __slots__ = ("changed", "going_in", "key", "site")

    def __init__(
        self, site: Site, going_in: tuple[GoingIn, ...], changed: tuple[str, ...], key: Key
    ) -> None:
        self.site = site
        self.going_in = going_in
        self.changed = changed
        self.key = key


class _Recording:
    """The live input's recording: where its runs go, and how far each piece has come."""

    __slots__ = ("done", "recorded", "runs", "sink", "text", "waiting")

    def __init__(self) -> None:
        self.sink: BranchSink | None = None
        self.clear()

    def clear(self) -> None:
        # the runs started of each piece, by its site
        self.runs: dict[_Site, int] = {}
        # the runs recorded of each piece, by its site
        self.recorded: dict[Site, int] = {}
        # by line, a piece whose runs are all started: the one tuple of its names its calls are
        # given, and its column
        self.done: dict[int, tuple[tuple[str, ...], int]] = {}
        # by line, each entry waiting on its exit
        self.waiting: Waiting[_Entry] = {}
        self.text = 0

    def entered(
        self,
        frame: types.FrameType,
        line: int,
        col: int,
        going_in: tuple[str, ...],
        changed: tuple[str, ...],
    ) -> _Entry | None:
        """A run of a piece starts in the frame: its entry, when it is among the piece's first
        runs and its values going in are kept, after any entry left in this frame is dropped."""
        with contextlib.suppress(Exception):
            key = (id(frame), col)
            popped(self.waiting, line, key)
            site = (frame.f_code.co_filename, line, col)
            started = self.runs.get(site, 0)
            names = going_in or changed
            if started + 1 >= MOST_RUNS and names:
                self.done[line] = (names, col)
            if started >= MOST_RUNS:
                return None
            self.runs[site] = started + 1
            values = _going_in(frame.f_locals, going_in)
            if values is None:
                return None
            entry = _Entry(Site(*site), values, changed, key)
            self.waiting.setdefault(line, {})[key] = entry
            return entry
        return None

    def left(
        self, frame: types.FrameType, line: int, col: int, changed: tuple[str, ...]
    ) -> int | None:
        """A loop's run ends in the frame: its run is recorded, when its entry waits on it. Its
        position among the piece's recorded runs, or None when it is not recorded."""
        with contextlib.suppress(Exception):
            entry = popped(self.waiting, line, (id(frame), col))
            if entry is None:
                return None
            values = _changed(frame.f_locals, changed)
            if values is not None:
                return self._record(PieceRun(entry.site, entry.going_in, values))
        return None

    def assigned(self, entry: _Entry, value: object) -> int | None:
        """An assignment's run ends with its value: its run is recorded, when its entry is still
        the one waiting. Its position among the piece's recorded runs, or None when it is not
        recorded."""
        with contextlib.suppress(Exception):
            waiting = self.waiting.get(entry.site.line)
            if waiting is None or waiting.get(entry.key) is not entry:
                return None
            popped(self.waiting, entry.site.line, entry.key)
            text = json_text(value, MOST_VALUE)
            if text is not None:
                changed = tuple(Changed(name, text) for name in entry.changed)
                return self._record(PieceRun(entry.site, entry.going_in, changed))
        return None

    def failed(self, run: Run, changed: tuple[Changed, ...] | None) -> int | None:
        """A run of a loop in use whose formula was dropped on it, that no entry recorded: its run
        is recorded, from the values that went in and the ``changed``. Its position among the
        piece's recorded runs, or None when it is not recorded."""
        with contextlib.suppress(Exception):
            going_in = _going_in(run.kept, run.names[0])
            if going_in is not None and changed is not None:
                return self._record(PieceRun(run.site, going_in, changed))
        return None

    def _record(self, run: PieceRun) -> int | None:
        """Append a run to the sink, when it fits in what the input's runs may count: its
        position among its piece's recorded runs, or None when it does not fit."""
        counted = size(run)
        if self.sink is None or self.text + counted > MOST_TEXT:
            return None
        self.text += counted
        at = self.recorded.get(run.site, 0)
        self.recorded[run.site] = at + 1
        self.sink.append(run)
        return at


_RECORDING = _Recording()


def start(sink: BranchSink, *, alone: bool = False) -> None:
    """An input goes live: from now on the hooks record its runs into ``sink``, from none, and,
    when its call runs ``alone`` in a process of its own, use the loops in use
    (`pyct.core.entry.in_use`)."""
    _RECORDING.clear()
    _RECORDING.sink = sink
    in_use.start(sink, alone=alone)


def forget() -> None:
    """The live input ends: the hooks record nothing until the next `start`."""
    _RECORDING.sink = None
    _RECORDING.clear()
    in_use.forget()


def counted(cost: int) -> bool:
    """Whether a run that counts ``cost`` by its own measure, such as a loss site's
    (`pyct.core.entry.losses`), fits in what the live input's recorded runs may count together,
    `MOST_TEXT`: counted when it does."""
    if _RECORDING.sink is None or _RECORDING.text + cost > MOST_TEXT:
        return False
    _RECORDING.text += cost
    return True


def size(run: PieceRun) -> int:
    """What a run counts against `MOST_TEXT`: the characters of its file, its names and its
    values, `RUN_COUNT` for the run and `VALUE_COUNT` for each value."""
    values = [(each.name, each.value) for each in run.going_in]
    values += [(each.name, each.value) for each in run.changed]
    counted = sum(len(name) + len(value) + VALUE_COUNT for name, value in values)
    return RUN_COUNT + len(run.site.file) + counted


def piece_over[Iterated](
    iterable: Iterated,
    line: int,
    col: int,
    going_in: tuple[str, ...],
    changed: tuple[str, ...],
    /,
    *,
    _recording: _Recording = _RECORDING,
) -> Iterated:
    """A ``for`` or ``async for`` starts: called once per run of the loop, with the iterable it
    was written with, after the iterable is evaluated and before Python asks it for an
    iterator. It hands back what the loop iterates over, the iterable itself."""
    if _recording.sink is None:
        return iterable
    # the piece's runs are all started, and no entry waits on its line for this one to drop: one
    # check written out, as each hook here, since a call would cost as much again
    done = _recording.done.get(line)
    if (
        done is None
        or done[0] is not (going_in or changed)
        or done[1] != col
        or line in _recording.waiting
    ):
        _recording.entered(sys._getframe(1), line, col, going_in, changed)
    if line in USING.lines:
        return in_use.over(iterable, sys._getframe(1), line, col, (going_in, changed))
    return iterable


def piece_in(
    line: int,
    col: int,
    going_in: tuple[str, ...],
    changed: tuple[str, ...],
    /,
    *,
    _recording: _Recording = _RECORDING,
) -> object:
    """A ``while`` or an assignment of a comprehension starts: called once per run, a
    ``while``'s before its test is first evaluated, an assignment's before its value is. It hands
    back a token, which an assignment hands to `piece_value` and a ``while`` drops: the run of
    a loop in use, the run's entry, or None for a run that records nothing."""
    if _recording.sink is None:
        return None
    entry = None
    done = _recording.done.get(line)
    if (
        done is None
        or done[0] is not (going_in or changed)
        or done[1] != col
        or line in _recording.waiting
    ):
        entry = _recording.entered(sys._getframe(1), line, col, going_in, changed)
    if line in USING.lines:
        run = in_use.entered(sys._getframe(1), line, col, (going_in, changed))
        if run is not None:
            run.entry = entry
            return run
    return entry


def piece_out(
    line: int,
    col: int,
    going_in: tuple[str, ...],
    changed: tuple[str, ...],
    /,
    *,
    _recording: _Recording = _RECORDING,
) -> None:
    """A loop's run ends, by exhaustion, by its test going false or by a ``break`` that leaves it:
    called once per run, after its last pass and before its ``else`` runs, or right before the
    ``break``. A run that ends by ``return`` or a raise calls it not at all, and a ``while True``
    only at a ``break``. It hands back None, which the caller drops."""
    at = (
        _recording.left(sys._getframe(1), line, col, changed)
        if line in _recording.waiting
        else None
    )
    if line in USING.waiting:
        frame = sys._getframe(1)
        dropped_run = in_use.left(frame, line, col)
        if dropped_run is not None:
            _ended_dropped(
                _recording, frame, dropped_run, at, lambda: _changed(frame.f_locals, changed)
            )


def piece_value[Value](
    token: object, value: Value, /, *, _recording: _Recording = _RECORDING
) -> Value:
    """An assignment of a comprehension ends: called once per run, with the token `piece_in` gave
    for this run and the value, before it is stored into the target, which is the piece's one
    changed name. It hands back the value to store, a tracked one for a loop in use."""
    if token is not None and type(token) is _Entry:
        _recording.assigned(token, value)
    elif type(token) is Run:
        entry = token.entry
        at = _recording.assigned(entry, value) if type(entry) is _Entry else None
        frame = sys._getframe(1)
        stored, was_dropped = in_use.assigned(frame, token, value)
        if was_dropped:
            _ended_dropped(_recording, frame, token, at, lambda: _stored(token, value))
        return cast(Value, stored)
    return value


def _ended_dropped(
    recording: _Recording,
    frame: types.FrameType,
    run: Run,
    at: int | None,
    changed_values: Callable[[], tuple[Changed, ...] | None],
) -> None:
    """A run whose formula was dropped on it ends in the frame: its names are restored and, when
    no entry recorded it (``at`` None), it is recorded with the values ``changed_values`` gives;
    its drop reaches the sink whatever either does."""
    try:
        in_use.restored(frame, run)
        if at is None:
            at = recording.failed(run, changed_values())
    finally:
        in_use.dropped(run, at)


def _stored(run: Run, value: object) -> tuple[Changed, ...] | None:
    """An assignment's changed name with the value it stores, as JSON text, or None when the
    value is not kept."""
    text = json_text(value, MOST_VALUE)
    return None if text is None else tuple(Changed(name, text) for name in run.names[1])


def _going_in(held: Mapping[str, object], names: tuple[str, ...]) -> tuple[GoingIn, ...] | None:
    """Each name bound in the frame's locals, its value as JSON text and whether it is tracked,
    or None when a value is not kept."""
    values = []
    for name in names:
        if name in held:
            value = held[name]
            text = json_text(value, MOST_VALUE)
            if text is None:
                return None
            values.append(GoingIn(name, text, type(value) in TRACKED_CLASSES))
    return tuple(values)


def _changed(held: Mapping[str, object], names: tuple[str, ...]) -> tuple[Changed, ...] | None:
    """Each name bound in the frame's locals, its value as JSON text, or None when a value is
    not kept."""
    values = []
    for name in names:
        if name in held:
            text = json_text(held[name], MOST_VALUE)
            if text is None:
                return None
            values.append(Changed(name, text))
    return tuple(values)

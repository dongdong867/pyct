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
a `PieceRun`. A run that ends by ``return`` or a raise calls no exit and
records nothing; the entry it left is dropped by the next entry of that
piece in that frame, and when the input ends. A run is recorded only when
each of its values is plain JSON data (`plain_json`) whose text is shorter
than `MOST_VALUE`, a tuple not being such data, and while it fits in what
the input's recorded runs may count together, `MOST_TEXT` by `size`. A
hook raises nothing of its own into the target, and reads each value
through its base type.

A hook that records nothing does little: with no input live it reads one
field, and past a piece's runs a lookup by its line. A piece that shares
its line with another piece whose runs are all started reads its frame on
each entry instead, as would one given no names at all, which
`pyct.intercept.loops` leaves as written; an exit reads its frame while an
entry waits on its line.
"""

from __future__ import annotations

import contextlib
import json
import sys
import types
from collections.abc import Mapping

from pyct.core.entry.bases import TRACKED_CLASSES
from pyct.core.entry.plain_json import plain_json
from pyct.core.foundation.branch import BranchSink, Changed, GoingIn, PieceRun, Site

# the runs of each piece recorded in an input, its first
MOST_RUNS = 3
# a recorded value's JSON text is shorter than this many characters, each one byte
MOST_VALUE = 2048
# what an input's recorded runs may count together, by `size`
MOST_TEXT = 1024 * 1024
# what `size` counts for each run, and for each value, beside their characters
RUN_COUNT, VALUE_COUNT = 64, 2

_dumps = json.dumps

type _Site = tuple[str, int, int]
# an entry waiting on its exit, by its frame's id and its column
type _Key = tuple[int, int]


class _Entry:
    """A run's entry, waiting on its exit: its site, its values going in, its changed names, and
    where it waits. An assignment's entry hook hands it back as the token its exit gets."""

    __slots__ = ("changed", "going_in", "key", "site")

    def __init__(
        self, site: Site, going_in: tuple[GoingIn, ...], changed: tuple[str, ...], key: _Key
    ) -> None:
        self.site = site
        self.going_in = going_in
        self.changed = changed
        self.key = key


class _Recording:
    """The live input's recording: where its runs go, and how far each piece has come."""

    __slots__ = ("done", "runs", "sink", "text", "waiting")

    def __init__(self) -> None:
        self.sink: BranchSink | None = None
        self.clear()

    def clear(self) -> None:
        # the runs started of each piece, by its site
        self.runs: dict[_Site, int] = {}
        # by line, a piece whose runs are all started: the one tuple of its names its calls are
        # given, and its column
        self.done: dict[int, tuple[tuple[str, ...], int]] = {}
        # by line, each entry waiting on its exit
        self.waiting: dict[int, dict[_Key, _Entry]] = {}
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
            self._drop(line, key)
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

    def left(self, frame: types.FrameType, line: int, col: int, changed: tuple[str, ...]) -> None:
        """A loop's run ends in the frame: its run is recorded, when its entry waits on it."""
        with contextlib.suppress(Exception):
            entry = self._drop(line, (id(frame), col))
            if entry is None:
                return
            values = _changed(frame.f_locals, changed)
            if values is not None:
                self._record(PieceRun(entry.site, entry.going_in, values))

    def assigned(self, entry: _Entry, value: object) -> None:
        """An assignment's run ends with its value: its run is recorded, when its entry is still
        the one waiting."""
        with contextlib.suppress(Exception):
            waiting = self.waiting.get(entry.site.line)
            if waiting is None or waiting.get(entry.key) is not entry:
                return
            self._drop(entry.site.line, entry.key)
            text = _text(value)
            if text is not None:
                changed = tuple(Changed(name, text) for name in entry.changed)
                self._record(PieceRun(entry.site, entry.going_in, changed))

    def _record(self, run: PieceRun) -> None:
        """Append a run to the sink, when it fits in what the input's runs may count."""
        counted = size(run)
        if self.sink is None or self.text + counted > MOST_TEXT:
            return
        self.text += counted
        self.sink.append(run)

    def _drop(self, line: int, key: _Key) -> _Entry | None:
        """Drop the entry waiting at the line by the key, and hand it back."""
        waiting = self.waiting.get(line)
        if waiting is None:
            return None
        entry = waiting.pop(key, None)
        if not waiting:
            del self.waiting[line]
        return entry


_RECORDING = _Recording()


def start(sink: BranchSink) -> None:
    """An input goes live: from now on the hooks record its runs into ``sink``, from none."""
    _RECORDING.clear()
    _RECORDING.sink = sink


def forget() -> None:
    """The live input ends: the hooks record nothing until the next `start`."""
    _RECORDING.sink = None
    _RECORDING.clear()


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
    back a token, which an assignment hands to `piece_value` and a ``while`` drops: the run's
    entry, or None for a run that records nothing."""
    if _recording.sink is None:
        return None
    done = _recording.done.get(line)
    if (
        done is None
        or done[0] is not (going_in or changed)
        or done[1] != col
        or line in _recording.waiting
    ):
        return _recording.entered(sys._getframe(1), line, col, going_in, changed)
    return None


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
    if line in _recording.waiting:
        _recording.left(sys._getframe(1), line, col, changed)


def piece_value[Value](
    token: object, value: Value, /, *, _recording: _Recording = _RECORDING
) -> Value:
    """An assignment of a comprehension ends: called once per run, with the token `piece_in` gave
    for this run and the value, before it is stored into the target, which is the piece's one
    changed name. It hands back the value to store."""
    if token is not None and type(token) is _Entry:
        _recording.assigned(token, value)
    return value


def _going_in(held: Mapping[str, object], names: tuple[str, ...]) -> tuple[GoingIn, ...] | None:
    """Each name bound in the frame's locals, its value as JSON text and whether it is tracked,
    or None when a value is not kept."""
    values = []
    for name in names:
        if name in held:
            value = held[name]
            text = _text(value)
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
            text = _text(held[name])
            if text is None:
                return None
            values.append(Changed(name, text))
    return tuple(values)


def _text(value: object) -> str | None:
    """The value's JSON text, or None when it is not plain JSON data or its text is not shorter
    than `MOST_VALUE`."""
    try:
        text = _dumps(plain_json(value, tuples=False, most=MOST_VALUE))
    except (TypeError, ValueError, RecursionError):
        return None
    return text if len(text) < MOST_VALUE else None

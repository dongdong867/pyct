"""The loops in use: a loop whose runs a checked formula stands for, in a call that runs in a
process of its own (`pyct.core.entry.pieces` calls this module from its hooks).

An upper layer puts each loop in use in `IN_USE`, by its file, line and
column, before an input starts; `start` reads it then. While the input is
live and its call runs alone, each run of a loop in use starts plain: each
name going in that is bound and holds a tracked int, float, str or bool is
rebound to its plain value, and a ``for`` over a tracked str walks the plain
str. Lists and dicts stay as they are; the run keeps a copy of each list
or dict going in. A copy of Python's own is one level deep. A tracked one's
copy is tracked, one level deep, while it has a form and its length is the
one pyct last saw. Otherwise its copy is plain, each tracked list or dict
inside it at every depth is a plain copy too, and each tracked int, float,
str or bool in them is its plain value. Either copy records nothing and
leaves the target's own as it is. The loop then runs on plain values and
records no fork.

At the run's end the formula is called on the tracked values that went in,
each list or dict as the copy the start made, each fork, fact and downgrade
it records placed at the loop's site, and each changed name the frame has
bound is compared with the formula's value of it by
their JSON text, which records nothing. On a match each changed name whose
formula value is a tracked int, float, str or bool holds the loop's own
value with the formula's term; another formula value leaves the loop's
value as it is. On a mismatch, a raise, or a changed name the formula gives
no value for, the changed names stay as the loop left them, the sink is
handed a `FormulaDrop` once the run is recorded (`dropped`), naming that
run, also when the restore or the record raises, and the loop is followed
as written for the rest of the input; a run of the loop still open then, in
an outer frame, ends with no call: its names
going in that it does not change get their tracked values back, and its
changed names keep the loop's values. Either way each name going in that is
not one of the piece's changed names gets its tracked value back when the
frame still holds the plain value the start wrote.

A raise that is not an ``Exception``, the deadline's, passes through. A run
that ends by ``return`` or a raise reaches no end: its names stay plain,
and the next start of the loop in that frame drops it.
"""

from __future__ import annotations

import contextlib
import copy
import dataclasses
import types
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import cast

from pyct.core.dicts.dicts import ConcolicDict
from pyct.core.entry.frames import rebind
from pyct.core.entry.waiting import Key, Waiting, json_text, popped
from pyct.core.foundation.branch import BranchSink, DropReason, FormulaDrop, Site, placed_at
from pyct.core.lists.list_state import plain
from pyct.core.lists.lists import ConcolicList
from pyct.core.numbers.bools import ConcolicBool
from pyct.core.numbers.floats import ConcolicFloat
from pyct.core.numbers.ints import ConcolicInt
from pyct.core.strs.strs import ConcolicStr

# the tracked values a loop in use runs on plain, and a formula's value hands on
_SCALARS = frozenset({ConcolicInt, ConcolicFloat, ConcolicStr, ConcolicBool})

type _Place = tuple[str, int, int]
# a piece's names going in and its changed names
type _Names = tuple[tuple[str, ...], tuple[str, ...]]


@dataclass(frozen=True)
class LoopInUse:
    """A loop's formula: its parameters, the names it gives a value, and the call that takes
    each parameter's value by name and answers each changed name's value by name."""

    parameters: tuple[str, ...]
    changed: tuple[str, ...]
    formula: Callable[[Mapping[str, object]], Mapping[str, object]]


# the loops in use, by the file, line and column of each
IN_USE: dict[_Place, LoopInUse] = {}


class Run:
    """A run of a loop in use, waiting on its end: the loop, the piece's names, the values that
    went in, each list or dict as a copy made then, the plain values its start wrote, and where
    it waits. ``entry`` is the token the
    recording of the piece's runs gave this run."""

    __slots__ = ("drop", "entry", "key", "kept", "loop", "names", "place", "site", "written")

    def __init__(
        self, place: _Place, loop: LoopInUse, names: _Names, kept: dict[str, object], key: Key
    ) -> None:
        self.place = place
        self.site = Site(*place)
        self.loop = loop
        self.names = names
        self.kept = {name: _as_it_went_in(each) for name, each in kept.items()}
        self.written = {name: plain(each) for name, each in kept.items() if type(each) in _SCALARS}
        self.key = key
        self.entry: object = None
        # the drop of the run's formula, until `dropped` hands it to the sink
        self.drop: FormulaDrop | None = None


class _Using:
    """The live input's loops in use: the lines they start at when its call uses them, none
    else, where its drops go, the loops dropped in it, and each run waiting on its end, by
    line."""

    __slots__ = ("dropped", "lines", "sink", "waiting")

    def __init__(self) -> None:
        self.lines: frozenset[int] = frozenset()
        self.sink: BranchSink | None = None
        self.clear()

    def clear(self) -> None:
        self.dropped: set[_Place] = set()
        self.waiting: Waiting[Run] = {}


USING = _Using()


def start(sink: BranchSink, *, alone: bool) -> None:
    """An input goes live: its call uses the loops in `IN_USE` now when it runs ``alone`` in a
    process of its own, and hands its drops to ``sink``."""
    USING.clear()
    USING.sink = sink
    USING.lines = frozenset(line for _, line, _ in IN_USE) if alone else frozenset()


def forget() -> None:
    """The live input ends: no loop is in use until the next `start`."""
    USING.lines = frozenset()
    USING.sink = None
    USING.clear()


def entered(frame: types.FrameType, line: int, col: int, names: _Names) -> Run | None:
    """A run of a piece starts in the frame: when the piece is a loop in use, its run, its
    tracked values going in rebound plain."""
    with contextlib.suppress(Exception):
        place = (frame.f_code.co_filename, line, col)
        key = (id(frame), col)
        popped(USING.waiting, line, key)
        loop = IN_USE.get(place)
        if loop is None or place in USING.dropped:
            return None
        held = frame.f_locals
        run = Run(place, loop, names, {name: held[name] for name in names[0] if name in held}, key)
        rebind(frame, run.written)
        USING.waiting.setdefault(line, {})[key] = run
        return run
    return None


def over[Iterated](
    iterable: Iterated, frame: types.FrameType, line: int, col: int, names: _Names
) -> Iterated:
    """A ``for`` starts in the frame, as `entered`: what it iterates over, a tracked str plain
    when the loop is in use."""
    run = entered(frame, line, col, names)
    if run is not None and type(iterable) is ConcolicStr:
        return cast(Iterated, plain(iterable))
    return iterable


def left(frame: types.FrameType, line: int, col: int) -> Run | None:
    """A loop's run ends in the frame: its formula stands for it, unless the input dropped the
    formula while the run was open, which only restores the names. Hands back the run when its
    formula was dropped on it, its names not yet restored (`restored`), else None."""
    with contextlib.suppress(Exception):
        run = popped(USING.waiting, line, (id(frame), col))
        if run is None:
            return None
        if run.place in USING.dropped:
            _rebound(frame, run, {})
            return None
        held = frame.f_locals
        real = {name: held[name] for name in run.loop.changed if name in held}
        made = _finished(run, real)
        if made is None:
            return run
        _rebound(frame, run, made)
    return None


def assigned(frame: types.FrameType, run: Run, value: object) -> tuple[object, bool]:
    """An assignment's run ends in the frame with its value, as `left`: the value to store, the
    tracked one when the formula matches, and whether the formula was dropped on it, the names
    then not yet restored (`restored`)."""
    with contextlib.suppress(Exception):
        line = run.site.line
        waiting = USING.waiting.get(line)
        if waiting is None or waiting.get(run.key) is not run:
            return value, False
        popped(USING.waiting, line, run.key)
        if run.place in USING.dropped:
            _rebound(frame, run, {})
            return value, False
        stored = run.loop.changed[0]
        made = _finished(run, {stored: value})
        if made is None:
            return value, True
        _rebound(frame, run, made)
        return made.get(stored, value), False
    return value, False


def _finished(run: Run, real: Mapping[str, object]) -> dict[str, object] | None:
    """Each changed name's tracked value the formula gives, or None when it is dropped."""
    loop = run.loop
    given = {name: run.kept[name] for name in loop.parameters if name in run.kept}
    try:
        got = placed_at(run.site, lambda: loop.formula(given))
    except Exception as error:
        return _dropped(run, real, next(iter(real), ""), type(error).__name__, DropReason.RAISED)
    made: dict[str, object] = {}
    for name, value in real.items():
        if not isinstance(got, Mapping) or name not in got:
            return _dropped(run, real, name, "", DropReason.MISSING)
        result = got[name]
        text = json_text(result)
        if text is None or text != json_text(value):
            return _dropped(run, real, name, text or "", DropReason.MISMATCH)
        if type(result) in _SCALARS:
            tracked = cast(ConcolicInt, result)
            # the loop's value is of the formula value's kind, as their JSON texts are one
            real_value = cast(int, plain(value))
            made[name] = type(tracked).made(real_value, tracked.expression, tracked.sink)
    return made


def _dropped(run: Run, real: Mapping[str, object], name: str, got: str, reason: DropReason) -> None:
    """Drop the run's loop for the rest of the input, and keep the drop with the run for
    `dropped`."""
    USING.dropped.add(run.place)
    value = json_text(real[name]) if name in real else None
    run.drop = FormulaDrop(run.site, name, value or "", got, reason)


def restored(frame: types.FrameType, run: Run) -> None:
    """A run whose formula was dropped on it ends in the frame: each name going in that is not
    one of the piece's changed names gets its tracked value back, as `_rebound` gives it."""
    with contextlib.suppress(Exception):
        _rebound(frame, run, {})


def dropped(run: Run, at: int | None) -> None:
    """Hand the sink the drop of the run's formula, once the run is recorded: ``at`` is its
    position among the input's recorded runs of the loop, None when it is not recorded."""
    with contextlib.suppress(Exception):
        drop = run.drop
        if drop is not None and USING.sink is not None:
            USING.sink.append(dataclasses.replace(drop, run=at))


def _rebound(frame: types.FrameType, run: Run, made: Mapping[str, object]) -> None:
    """Bind each changed name the formula gave a tracked value, and give each name going in that
    is not one of the piece's changed names its tracked value back where the frame still holds
    the plain value the start wrote. A changed name the formula gave none keeps the loop's
    value."""
    held = frame.f_locals
    back = dict(made)
    changed = run.names[1]
    for name, written in run.written.items():
        if name not in changed and name in held and held[name] is written:
            back[name] = run.kept[name]
    rebind(frame, back)


def _as_it_went_in(value: object) -> object:
    """A list or dict going in as a copy of the list or dict itself, one level deep, taken on
    every run of a loop in use: a loop that adds, removes or replaces its items leaves the copy
    as it went in. A tracked one's copy is tracked by the same form and records no fork. One
    with no form, or whose length is not the one pyct last saw, gets a plain copy
    (`_plain_copy`), which records nothing and leaves the target's own as it is. The copy costs
    about 4 microseconds for a tracked list of 100 items and 40 for 1,000. Any other value as it
    is."""
    kind = type(value)
    if kind is ConcolicList:
        items = cast(ConcolicList, value)
        current = items.expression is not None and items.length() == len(items.shadow)
        return copy.copy(items) if current else _plain_copy(items, {})
    if kind is ConcolicDict:
        pairs = cast(ConcolicDict, value)
        current = pairs.expression is not None and pairs.size() == len(pairs.shadow)
        return copy.copy(pairs) if current else _plain_copy(pairs, {})
    if kind is list or kind is dict:
        return copy.copy(value)
    return value


def _plain_copy(value: object, made: dict[int, object]) -> object:
    """A tracked list or dict as a new plain one, and each tracked list or dict it holds, at
    every depth, as one too, each made once by its id in ``made``, so a list that holds itself
    holds its copy. Each tracked int, float, str and bool in them is its plain value, and any
    other item is the one the tracked list or dict holds. Each is read through its storage, so
    nothing is recorded."""
    kind = type(value)
    if kind is not ConcolicList and kind is not ConcolicDict:
        return plain(value)
    copied = made.get(id(value))
    if copied is not None:
        return copied
    if kind is ConcolicList:
        items: list[object] = []
        made[id(value)] = items
        items.extend(_plain_copy(item, made) for item in cast(ConcolicList, value).storage())
        return items
    pairs: dict[object, object] = {}
    made[id(value)] = pairs
    for key, each in cast(ConcolicDict, value).storage().items():
        pairs[key] = _plain_copy(each, made)
    return pairs

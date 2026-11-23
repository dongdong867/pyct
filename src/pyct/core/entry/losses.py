"""The runs of each loss site an input records, with summaries switched on.

A loss site is the site of a downgrade of one of three kinds (`LossKind`):
an operation pyct has not taught on a tracked int, float, bool or str, in
any code, which `pyct.core.foundation.values` hands on through the slot
`start` fills (`HEARS`); a `math` call pyct does not follow
(`pyct.core.entry.math_calls`); and a watched call
(`pyct.core.entry.watch`). While an input that records them is live, from
`start` to `forget`, each of the first `MOST_RUNS` runs of each site in
that input is recorded into the sink `start` was given, as a `LossRun`:
each value going in, by its position, as JSON text and whether it was a
tracked value, and the answer the target got. An operation's values going
in are its receiver, then its other operands and arguments, read after the
operation; a watched call's are the arguments the watch was given, each
written as JSON text when it was given, while its call has started fewer
than `MOST_RUNS` times in the input. A run is kept only when each value is
plain JSON data shorter than `MOST_VALUE`, a tuple not being such data, and
while it fits in what the input's recorded runs count together with the
pieces' runs (`pyct.core.entry.pieces.counted`). When two downgrade names
share a site, the first one recorded there is the site's. Nothing here
raises into the target.
"""

from __future__ import annotations

import contextlib
import types
from collections.abc import Callable

from pyct.core.entry import pieces
from pyct.core.entry.bases import TRACKED_CLASSES
from pyct.core.entry.pieces import MOST_RUNS, MOST_VALUE, RUN_COUNT, VALUE_COUNT
from pyct.core.entry.waiting import json_text
from pyct.core.foundation.branch import (
    BranchSink,
    Callee,
    Changed,
    Downgrade,
    GoingIn,
    LossKind,
    LossRun,
    Site,
)
from pyct.core.foundation.heard_losses import HEARS
from pyct.core.numbers.bools import ConcolicBool
from pyct.core.numbers.floats import ConcolicFloat
from pyct.core.numbers.ints import ConcolicInt
from pyct.core.strs.strs import ConcolicStr

# the one changed name of a loss run
ANSWER = "answer"
# the receivers whose untaught operations are loss sites
_SCALARS = frozenset({ConcolicInt, ConcolicFloat, ConcolicBool, ConcolicStr})
_type = type


class _Losses:
    """The live input's recording: where its runs go, the first name at each site, the runs
    tried at each site, and how often each watched call started, by its frame's code and
    instruction."""

    __slots__ = ("calls", "codes", "names", "sink", "tried")

    def __init__(self) -> None:
        self.sink: BranchSink | None = None
        self.clear()

    def clear(self) -> None:
        self.names: dict[Site, str] = {}
        self.tried: dict[Site, int] = {}
        self.calls: dict[tuple[int, int], int] = {}
        # each code a watched call's start is counted by, held so its id stays its own
        self.codes: list[types.CodeType] = []


_LOSSES = _Losses()


def start(sink: BranchSink) -> None:
    """An input that records loss runs goes live: from now on each site's runs go into ``sink``,
    from none."""
    _LOSSES.clear()
    _LOSSES.sink = sink
    HEARS[0] = _operation


def forget() -> None:
    """The live input ends: nothing is recorded until the next `start`."""
    HEARS[0] = None
    _LOSSES.sink = None
    _LOSSES.clear()


def _operation(lost: Downgrade, operands: tuple[object, ...], answer: object) -> None:
    """An operation's loss, on a tracked receiver, ``operands[0]``."""
    if operands and _type(operands[0]) in _SCALARS:
        _record(lost, LossKind.OPERATION, lambda: _values(operands), answer)


def math_lost(lost: Downgrade, args: tuple[object, ...], answer: object) -> None:
    """A `math` call's loss, given its arguments, by position then by keyword."""
    if _LOSSES.sink is not None:
        _record(lost, LossKind.MATH, lambda: _values(args), answer)


def watching(frame: types.FrameType) -> list[GoingIn] | None:
    """A watched call starts in ``frame``: the list its arguments are written into as the watch
    is given them, while the call has started fewer than `MOST_RUNS` times in the live input;
    else None."""
    if _LOSSES.sink is None:
        return None
    with contextlib.suppress(Exception):
        code = frame.f_code
        key = (id(code), frame.f_lasti)
        started = _LOSSES.calls.get(key, 0)
        if started >= MOST_RUNS:
            return None
        if not started:
            _LOSSES.codes.append(code)
        _LOSSES.calls[key] = started + 1
        return []
    return None


def written(values: list[GoingIn], value: object) -> list[GoingIn] | None:
    """``values`` with an argument the watch was given added, as JSON text, or None when it is not
    kept."""
    with contextlib.suppress(Exception):
        text = json_text(value, MOST_VALUE)
        if text is not None:
            values.append(GoingIn(f"arg{len(values) + 1}", text, _type(value) in TRACKED_CLASSES))
            return values
    return None


def call_lost(
    lost: Downgrade, values: list[GoingIn] | None, answer: object, callee: object
) -> None:
    """A watched call's loss: the arguments the watch wrote, its answer and its callee."""
    if _LOSSES.sink is not None and values is not None:
        _record(lost, LossKind.CALL, lambda: tuple(values), answer, callee)


def _record(
    lost: Downgrade,
    kind: LossKind,
    going_in: Callable[[], tuple[GoingIn, ...] | None],
    answer: object,
    callee: object = None,
) -> None:
    """Record a run of the site, when it is among its first runs, its name is the site's, and
    its values are kept and fit. ``going_in`` gives the values going in, or None."""
    sink = _LOSSES.sink
    with contextlib.suppress(Exception):
        site = lost.site
        if sink is None or _LOSSES.names.setdefault(site, lost.name) != lost.name:
            return
        tried = _LOSSES.tried.get(site, 0)
        if tried >= MOST_RUNS:
            return
        _LOSSES.tried[site] = tried + 1
        values = going_in()
        text = json_text(answer, MOST_VALUE)
        if values is None or text is None:
            return
        named = None if kind is not LossKind.CALL else callee_of(callee)
        run = LossRun(site, lost.name, kind, values, (Changed(ANSWER, text),), named)
        if pieces.counted(size(run)):
            sink.append(run)


def _values(operands: tuple[object, ...]) -> tuple[GoingIn, ...] | None:
    """Each operand as a value going in, by its position, or None when one is not kept."""
    values = []
    for at, value in enumerate(operands, start=1):
        text = json_text(value, MOST_VALUE)
        if text is None:
            return None
        values.append(GoingIn(f"arg{at}", text, _type(value) in TRACKED_CLASSES))
    return tuple(values)


def callee_of(callee: object) -> Callee | None:
    """A watched call's callee by its module and qualified name, and a Python function's code's
    file and first line, read through Python's own types alone, so no code of the target's runs:
    a bound method's function, a function, a function or a method written in C, or a class;
    else the callee's own type's names."""
    target = callee.__func__ if _type(callee) is types.MethodType else callee  # pyrefly: ignore[missing-attribute]
    kind = _type(target)
    if kind is types.FunctionType:
        code = target.__code__  # pyrefly: ignore[missing-attribute]
        module = target.__module__  # pyrefly: ignore[missing-attribute]
        qualname = target.__qualname__  # pyrefly: ignore[missing-attribute]
        return Callee(str(module), str(qualname), code.co_filename, code.co_firstlineno)
    if kind is types.BuiltinFunctionType:
        owner = target.__self__  # pyrefly: ignore[missing-attribute]
        module = target.__module__ or _type(owner).__module__  # pyrefly: ignore[missing-attribute]
        return Callee(str(module), str(target.__qualname__))  # pyrefly: ignore[missing-attribute]
    if kind in _DESCRIPTORS:
        owner = target.__objclass__  # pyrefly: ignore[missing-attribute]
        return Callee(_TYPE_MODULE(owner), str(target.__qualname__))  # pyrefly: ignore[missing-attribute]
    named = target if issubclass(kind, type) else kind
    return Callee(_TYPE_MODULE(named), _TYPE_QUALNAME(named))


# the methods written in C that a class holds, which name the class they belong to
_DESCRIPTORS = frozenset(
    {types.MethodDescriptorType, types.WrapperDescriptorType, types.ClassMethodDescriptorType}
)
# a class's module and qualified name, read as `type` keeps them, past any metaclass's lookup
_TYPE_MODULE = type.__dict__["__module__"].__get__
_TYPE_QUALNAME = type.__dict__["__qualname__"].__get__


def size(run: LossRun) -> int:
    """What a run counts against `pyct.core.entry.pieces.MOST_TEXT`: the characters of its file,
    its name, its kind, its names and values and its callee's names, `RUN_COUNT` for the run
    and `VALUE_COUNT` for each value."""
    values = [(each.name, each.value) for each in run.going_in]
    values += [(each.name, each.value) for each in run.changed]
    counted = sum(len(name) + len(value) + VALUE_COUNT for name, value in values)
    callee = run.callee
    named = 0 if callee is None else len(callee.module) + len(callee.qualname)
    named += 0 if callee is None or callee.file is None else len(callee.file) + 20
    fixed = RUN_COUNT + len(run.site.file) + len(run.name) + len(run.kind)
    return fixed + counted + named

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

Each loss goes first to the loss sites in use (`pyct.core.entry.calls_in_use`),
which hand back what the target gets: the real answer, or at a site in use
the real answer tracked, which records no downgrade. The run a site's
formula is dropped on is recorded also past the first `MOST_RUNS`, and the
drop follows it in the sink, with the run's position among the input's
recorded runs of the site. While a formula runs, a loop's or a site's, no
run is recorded.
"""

from __future__ import annotations

import contextlib
import dataclasses
import types
from collections.abc import Callable, Sequence

from pyct.core.entry import in_use
from pyct.core.entry.bases import TRACKED_CLASSES
from pyct.core.entry.in_use import ANSWER, CALLS_IN_USE
from pyct.core.entry.recorded import MOST_RUNS, MOST_VALUE, RUN_COUNT, VALUE_COUNT
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

# the receivers whose untaught operations are loss sites
_SCALARS = frozenset({ConcolicInt, ConcolicFloat, ConcolicBool, ConcolicStr})
_type = type


class _Losses:
    """The live input's recording: where its runs go, the first name at each site, the runs
    tried and the runs kept at each site, how often each watched call started, by its
    frame's code and instruction, and the files that hold a loss site in use, none unless its
    call runs alone."""

    __slots__ = ("calls", "codes", "files", "kept", "names", "sink", "tried")

    def __init__(self) -> None:
        self.sink: BranchSink | None = None
        self.files: frozenset[str] = frozenset()
        self.clear()

    def clear(self) -> None:
        self.names: dict[Site, str] = {}
        self.tried: dict[Site, int] = {}
        self.kept: dict[Site, int] = {}
        self.calls: dict[tuple[int, int], int] = {}
        # each code a watched call's start is counted by, held so its id stays its own
        self.codes: list[types.CodeType] = []


_LOSSES = _Losses()
# core's module of the loss sites in use, once loaded (`load_calls_in_use`)
_CALLS: list[types.ModuleType | None] = [None]


def start(sink: BranchSink, *, alone: bool = False) -> None:
    """An input that records loss runs goes live: from now on each site's runs go into ``sink``,
    from none, and its call uses the loss sites in use when it runs ``alone`` in a process of
    its own (`pyct.core.entry.calls_in_use`)."""
    _LOSSES.clear()
    _LOSSES.sink = sink
    HEARS[0] = _operation
    _LOSSES.files = frozenset()
    if alone and CALLS_IN_USE:
        sites = load_calls_in_use()
        sites.start(alone=True)
        _LOSSES.files = sites.LIVE.files


def forget() -> None:
    """The live input ends: nothing is recorded until the next `start`."""
    HEARS[0] = None
    _LOSSES.sink = None
    _LOSSES.clear()
    if _LOSSES.files:
        load_calls_in_use().forget()
        _LOSSES.files = frozenset()


def load_calls_in_use() -> types.ModuleType:
    """Core's module of the loss sites in use, imported the first time only, so that a plain run
    loads none of it: by an upper layer as a site first comes into use in pyct's own process,
    so that each forked input has it, or as a fresh interpreter is handed one, else by `start`."""
    module = _CALLS[0]
    if module is None:
        from pyct.core.entry import calls_in_use

        module = _CALLS[0] = calls_in_use
    return module


def watched_in(file: str) -> bool:
    """Whether ``file`` holds a loss site in use in the live input, so that a watched call there
    keeps its arguments as it is given them."""
    return file in _LOSSES.files


def keeps_given(code: types.CodeType, at: int) -> bool:
    """Whether a watched call that starts at instruction ``at`` of ``code``, in a file
    `watched_in` names, keeps its arguments (`pyct.core.entry.calls_in_use.keeps_given`)."""
    return load_calls_in_use().keeps_given(code, at)


def answered_at(code: types.CodeType, at: int, site: Site) -> None:
    """A watched call that kept its arguments answered at ``site``
    (`pyct.core.entry.calls_in_use.answered_at`)."""
    load_calls_in_use().answered_at(code, at, site)


def _operation(lost: Downgrade, operands: tuple[object, ...], answer: object) -> object:
    """An operation's loss, on a tracked receiver, ``operands[0]``: what the target gets."""
    if not operands or _type(operands[0]) not in _SCALARS:
        return answer
    return _heard(
        lost, operands, answer, lambda: _run(lost, LossKind.OPERATION, _values(operands), answer)
    )


def math_lost(lost: Downgrade, args: tuple[object, ...], answer: object) -> object:
    """A `math` call's loss, given its arguments, by position then by keyword: what the target
    gets."""
    if _LOSSES.sink is None:
        return answer
    return _heard(lost, args, answer, lambda: _run(lost, LossKind.MATH, _values(args), answer))


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
    lost: Downgrade,
    values: list[GoingIn] | None,
    answer: object,
    callee: object,
    given: list[object] | None = None,
) -> object:
    """A watched call's loss: the arguments the watch wrote, its answer, its callee, and, at a
    file that holds a loss site in use, the arguments as it was given them. What the target
    gets. Past the call's first starts the watch writes none, and its run, recorded only when a
    formula is dropped on it, is written from the arguments as it was given them."""
    if _LOSSES.sink is None or (values is None and given is None):
        return answer

    def run() -> LossRun | None:
        kept = values if values is not None else _all_written(given or [])
        if kept is None:
            return None
        return _run(lost, LossKind.CALL, tuple(kept), answer, callee_of(callee))

    return _heard(lost, given, answer, run)


def _all_written(given: list[object]) -> list[GoingIn] | None:
    """Each argument as `written` writes it, or None when one is not kept."""
    values: list[GoingIn] | None = []
    for value in given:
        if values is None:
            return None
        values = written(values, value)
    return values


def _heard(
    lost: Downgrade,
    given: Sequence[object] | None,
    answer: object,
    run: Callable[[], LossRun | None] | None,
) -> object:
    """A loss heard: what the target gets at a site in use (`calls_in_use.answered`), the run
    recorded by ``run`` when it gives one, and the formula's drop after it. With ``run`` None the
    run is not recorded."""
    got, drop = answer, None
    if _LOSSES.files:
        got, drop = load_calls_in_use().answered(lost, given, answer)
    at = None if run is None else _record(lost, run, past=drop is not None)
    sink = _LOSSES.sink
    if drop is not None and sink is not None:
        with contextlib.suppress(Exception):
            sink.append(dataclasses.replace(drop, run=at))
    return got


def _record(lost: Downgrade, run: Callable[[], LossRun | None], *, past: bool) -> int | None:
    """Record a run of the site, when it is among its first runs, or ``past`` them as the run a
    formula was dropped on, its name is the site's, no formula is running, and its values are
    kept and fit: its position among the input's recorded runs of the site, else None."""
    sink = _LOSSES.sink
    with contextlib.suppress(Exception):
        site = lost.site
        if sink is None or in_use.USING.forming:
            return None
        if _LOSSES.names.setdefault(site, lost.name) != lost.name:
            return None
        tried = _LOSSES.tried.get(site, 0)
        if tried >= MOST_RUNS and not past:
            return None
        _LOSSES.tried[site] = tried + 1
        made = run()
        # imported here, once a run is kept, so that a plain import loads no hook of a piece
        from pyct.core.entry import pieces

        if made is None or not pieces.counted(size(made)):
            return None
        sink.append(made)
        at = _LOSSES.kept.get(site, 0)
        _LOSSES.kept[site] = at + 1
        return at
    return None


def _run(
    lost: Downgrade,
    kind: LossKind,
    values: tuple[GoingIn, ...] | None,
    answer: object,
    callee: Callee | None = None,
) -> LossRun | None:
    """The run of the site, or None when its values or its answer are not kept."""
    text = json_text(answer, MOST_VALUE)
    if values is None or text is None:
        return None
    return LossRun(lost.site, lost.name, kind, values, (Changed(ANSWER, text),), callee)


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
    """What a run counts against `pyct.core.entry.recorded.MOST_TEXT`: the characters of its file,
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

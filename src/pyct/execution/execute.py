"""Call the target once and report the lines it ran."""

from __future__ import annotations

import contextlib
import inspect
import sys
import types
from collections.abc import Callable, Generator, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, field

from pyct.binding.annotations import Check
from pyct.binding.bind import bind
from pyct.binding.call import call_arguments
from pyct.core.branch import Branch, Fact
from pyct.execution.blame import blame, one_line
from pyct.execution.deadline import DeadlineError, close, deadline
from pyct.execution.tally import Tally, Watch, too_long
from pyct.results.failure import Failure, FailureKind
from pyct.results.record import DowngradeCount

# 3 and 4 are unassigned; 0, 1, 2, 5 belong to a debugger, coverage, a profiler, the optimizer
_TOOL_IDS = (3, 4, 0, 1, 2, 5)


@dataclass(frozen=True)
class ExecutionContext:
    """What stays fixed across calls: the callable, the file whose lines count, and what a raise is.

    ``alone`` says each call has its process to itself, as in a child process
    pyct starts for one input. No Ctrl-C reaches such a call as a raise, so a
    KeyboardInterrupt, or another BaseException that is neither an Exception
    nor SystemExit, is a raise like any other and ends the call as one. In
    pyct's own process it may be the person's Ctrl-C, so it passes through.

    ``positional`` is the parameters the call passes by position, read once
    from the signature ``load_target`` took; with none, every value goes by
    name. ``checks`` is what each parameter's annotation asks, which says the
    key type of each dict the call binds.
    """

    fn: Callable[..., object]
    file: str
    alone: bool = False
    positional: tuple[inspect.Parameter, ...] = ()
    checks: Mapping[str, Check] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionResult:
    """What one call did: the lines it reached, the forks it took, and how it ended.

    On a failure the lines, forks and facts are those reached before it. ``facts`` are what its
    path holds beside the forks, each placed after the forks recorded before it.
    """

    lines: frozenset[int]
    branches: tuple[Branch, ...]
    downgrades: tuple[DowngradeCount, ...] = ()
    failure: Failure | None = None
    facts: tuple[Fact, ...] = ()


def execute(
    ctx: ExecutionContext,
    args: Mapping[str, object],
    until: float | None = None,
    watch: Watch | None = None,
) -> ExecutionResult:
    """Call ``ctx.fn`` on the seed under a line tracer limited to ``ctx.file``.

    ``until`` is the monotonic instant the call must end by, or ``None``
    for no bound. execute takes the raw seed and binds it here, because the
    sink belongs to one call and nothing outside this function needs it.
    ``run()`` stays assembly. A raise in the target is a failure on the
    result, not an exception here; ``KeyboardInterrupt`` is the person's
    and passes through, unless the call is ``ctx.alone`` in its process.

    ``watch`` hears each fork, line and downgrade the moment the call makes
    it, so a caller whose process can die mid-call keeps what the call did.
    """
    tally = Tally(watch)
    tally.go_live()
    bound = bind(args, tally, ctx.checks)
    tracer = _LineTracer(ctx.file, tally)
    tracer.start()
    block = deadline(until)
    try:
        ending = _call(ctx, bound, block)
    finally:
        try:
            tracer.stop()
        finally:
            # from this frame, which called the block's, where the alarm never raises
            close(block)
    # sealed before the failure is written: writing it asks the raise for its text, which
    # asks any tracked value in it for its own, and that call is pyct's, not the target's
    tally.seal()
    return ExecutionResult(
        lines=frozenset(tally.lines),
        branches=tuple(tally.branches),
        downgrades=tally.counted(),
        failure=_ended(tally, _failure(ctx.fn, ending)),
        facts=tuple(tally.facts),
    )


@dataclass(frozen=True)
class _Ending:
    """How the call ended: the raise that ended it, if any, and whether the target was reached.

    ``called`` says whether the target was reached: a target that runs in
    C leaves no frame, so blame cannot read that from the traceback.
    """

    error: BaseException | None
    called: bool


def _call(
    ctx: ExecutionContext, bound: Mapping[str, object], block: AbstractContextManager[None]
) -> _Ending:
    """Call the target inside the deadline's ``block`` and keep how it ended, for ``_failure``
    to write once the sink is read.

    A positional-only parameter is passed by position, as ``ctx.positional``
    names it.
    """
    positional, keywords = call_arguments(ctx.positional, bound)
    called = False
    caught = BaseException if ctx.alone else (DeadlineError, SystemExit, Exception)
    try:
        # the limit goes back after the block, where no alarm of the call's can land
        with _room_below(_depth(sys._getframe()) - 1), block:
            called = True
            ctx.fn(*positional, **keywords)
    except caught as error:
        return _Ending(error=error, called=called)
    return _Ending(error=None, called=called)


@contextlib.contextmanager
def _room_below(frames: int) -> Generator[None]:
    """Raise the recursion limit by the ``frames`` pyct holds below the target while it runs.

    Called from a module's top level, a target's first frame sits on one
    frame; under pyct it sits on pyct's own. The limit grows by those frames
    alone, so the target's own frames get the room plain Python gives them
    below its first frame. The limit comes back after the call, unless the
    target set one of its own meanwhile, which stays.
    """
    before = sys.getrecursionlimit()
    raised = before + frames
    sys.setrecursionlimit(raised)
    try:
        yield
    finally:
        if sys.getrecursionlimit() == raised:
            sys.setrecursionlimit(before)


def _depth(frame: types.FrameType | None) -> int:
    """How many frames the stack holds from ``frame`` down, ``frame`` included."""
    depth = 0
    while frame is not None:
        depth += 1
        frame = frame.f_back
    return depth


def _ended(tally: Tally, failure: Failure | None) -> Failure | None:
    """How the call ended as its line says: ``too_long`` once it went past the forks a call
    keeps, unless pyct failed, since a pyct bug must reach the exit code."""
    if tally.past_bound and (failure is None or failure.kind is not FailureKind.PYCT_BUG):
        return too_long()
    return failure


def _failure(fn: Callable[..., object], ending: _Ending) -> Failure | None:
    """The failure a raise ended the call with, or None for a call that returned."""
    error = ending.error
    # the alarm can land in pyct's own frames too, so the kind is by type, before the rest
    if isinstance(error, DeadlineError):
        # only a fired alarm reaches here, and those tests run without coverage
        return Failure(kind=FailureKind.TIMEOUT, detail="deadline passed")  # pragma: no cover
    if isinstance(error, SystemExit):
        return Failure(kind=FailureKind.SYSTEM_EXIT, detail=one_line(error))
    if error is not None:
        return blame(fn, error, called=ending.called)
    return None


class _LineTracer:
    """Collect LINE events for one file through ``sys.monitoring``.

    ``sys.monitoring`` rather than ``sys.settrace``: the callback returns
    DISABLE for every code object outside the file, so frames in the
    stdlib and in pyct itself cost nothing after their first line. It
    needs a tool id nobody else holds, taken at start and freed at stop.
    """

    def __init__(self, file: str, tally: Tally) -> None:
        self.file = file
        self.tally = tally
        self.seen = tally.lines
        self.tool_id: int | None = None

    def start(self) -> None:
        monitoring = sys.monitoring
        self.tool_id = unused_tool_id()
        monitoring.use_tool_id(self.tool_id, "pyct")
        monitoring.register_callback(self.tool_id, monitoring.events.LINE, self._on_line)
        monitoring.set_events(self.tool_id, monitoring.events.LINE)

    def stop(self) -> None:
        if self.tool_id is None:
            return
        monitoring = sys.monitoring
        monitoring.set_events(self.tool_id, 0)
        monitoring.register_callback(self.tool_id, monitoring.events.LINE, None)
        monitoring.free_tool_id(self.tool_id)
        self.tool_id = None

    def _on_line(self, code: types.CodeType, line: int) -> object:
        if code.co_filename != self.file:
            return sys.monitoring.DISABLE
        # a line seen before costs one set lookup, as it did before the tally
        if line not in self.seen:
            self.tally.line(line)
        return None


def unused_tool_id() -> int:
    """A ``sys.monitoring`` tool id no one holds, the unassigned ones first."""
    for tool_id in _TOOL_IDS:
        if sys.monitoring.get_tool(tool_id) is None:
            return tool_id
    raise RuntimeError("every sys.monitoring tool id is taken")

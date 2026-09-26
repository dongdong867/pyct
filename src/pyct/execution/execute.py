"""Call the target once and report the lines it ran."""

from __future__ import annotations

import sys
import types
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from pyct.binding.bind import bind
from pyct.core.branch import Branch
from pyct.execution.blame import blame, one_line
from pyct.execution.deadline import DeadlineError, deadline
from pyct.execution.tally import Tally, Watch
from pyct.results.failure import Failure, FailureKind
from pyct.results.record import DowngradeCount

# 3 and 4 are unassigned; 0, 1, 2, 5 belong to a debugger, coverage, a profiler, the optimizer
_TOOL_IDS = (3, 4, 0, 1, 2, 5)


@dataclass(frozen=True)
class ExecutionContext:
    """What stays fixed across calls: the callable and the file whose lines count."""

    fn: Callable[..., object]
    file: str


@dataclass(frozen=True)
class ExecutionResult:
    """What one call did: the lines it reached, the forks it took, and how it ended.

    On a failure the lines and forks are those reached before it.
    """

    lines: frozenset[int]
    branches: tuple[Branch, ...]
    downgrades: tuple[DowngradeCount, ...] = ()
    failure: Failure | None = None


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
    and passes through.

    ``watch`` hears each fork, line and downgrade the moment the call makes
    it, so a caller whose process can die mid-call keeps what the call did.
    """
    tally = Tally(watch)
    bound = bind(args, tally)
    tracer = _LineTracer(ctx.file, tally)
    tracer.start()
    try:
        ending = _call(ctx.fn, bound, until)
    finally:
        tracer.stop()
    # sealed before the failure is written: writing it asks the raise for its text, which
    # asks any tracked value in it for its own, and that call is pyct's, not the target's
    tally.seal()
    return ExecutionResult(
        lines=frozenset(tally.lines),
        branches=tuple(tally.branches),
        downgrades=tally.counted(),
        failure=_failure(ctx.fn, ending),
    )


@dataclass(frozen=True)
class _Ending:
    """How the call ended: the raise that ended it, if any, and whether the target was reached.

    ``called`` says whether the target was reached: a target that runs in
    C leaves no frame, so blame cannot read that from the traceback.
    """

    error: BaseException | None
    called: bool


def _call(fn: Callable[..., object], bound: Mapping[str, object], until: float | None) -> _Ending:
    """Call the target and keep how it ended, for ``_failure`` to write once the sink is read."""
    called = False
    try:
        with deadline(until):
            called = True
            fn(**bound)
    except (DeadlineError, SystemExit, Exception) as error:
        return _Ending(error=error, called=called)
    return _Ending(error=None, called=called)


def _failure(fn: Callable[..., object], ending: _Ending) -> Failure | None:
    """The failure a raise ended the call with, or None for a call that returned."""
    error = ending.error
    # the timer can land in pyct's own frames too, so the kind is by type, before the rest
    if isinstance(error, DeadlineError):
        # only a fired alarm reaches here, and those tests run without coverage
        return Failure(kind=FailureKind.TIMEOUT, detail="deadline passed")  # pragma: no cover
    if isinstance(error, SystemExit):
        return Failure(kind=FailureKind.SYSTEM_EXIT, detail=one_line(error))
    if isinstance(error, Exception):
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
        self.tool_id = _free_tool_id()
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


def _free_tool_id() -> int:
    for tool_id in _TOOL_IDS:
        if sys.monitoring.get_tool(tool_id) is None:
            return tool_id
    raise RuntimeError("every sys.monitoring tool id is taken")

"""Call the target once and report the lines it ran."""

from __future__ import annotations

import sys
import traceback
import types
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from pyct.binding.bind import bind
from pyct.core.branch import Branch
from pyct.execution.deadline import DeadlineError
from pyct.execution.deadline import deadline as deadline_timer
from pyct.results.failure import Failure, FailureKind

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
    downgrades: tuple[str, ...] = ()
    failure: Failure | None = None


def execute(
    ctx: ExecutionContext, args: Mapping[str, object], deadline: float | None = None
) -> ExecutionResult:
    """Call ``ctx.fn`` on the seed under a line tracer limited to ``ctx.file``.

    ``deadline`` is the monotonic instant the call must end by, or ``None``
    for no bound. execute takes the raw seed and binds it here, because the
    sink belongs to one call and nothing outside this function needs it.
    ``run()`` stays assembly. A raise in the target is a failure on the
    result, not an exception here; ``KeyboardInterrupt`` is the person's
    and passes through.
    """
    sink: list[Branch] = []
    bound = bind(args, sink)
    tracer = _LineTracer(ctx.file)
    tracer.start()
    try:
        failure = _call(ctx.fn, bound, deadline)
    finally:
        tracer.stop()
    return ExecutionResult(lines=frozenset(tracer.seen), branches=tuple(sink), failure=failure)


def _call(
    fn: Callable[..., object], bound: Mapping[str, object], deadline: float | None
) -> Failure | None:
    """Call the target and say how it ended."""
    try:
        with deadline_timer(deadline):
            fn(**bound)
    # the timer can land in pyct's own frames too, so the kind is by type, before the rest
    except DeadlineError:
        return Failure(kind=FailureKind.TIMEOUT, detail="deadline passed")
    except SystemExit as error:
        return Failure(kind=FailureKind.SYSTEM_EXIT, detail=_one_line(error))
    except Exception as error:
        return Failure(kind=FailureKind.TARGET_RAISED, detail=_one_line(error))
    return None


def _one_line(error: BaseException) -> str:
    """The exception as a person reads it at the end of a traceback, on one line."""
    # a message with newlines comes back inside one entry, so split each entry too
    parts = (
        part.strip()
        for entry in traceback.format_exception_only(error)
        for part in entry.splitlines()
    )
    return " ".join(part for part in parts if part)


class _LineTracer:
    """Collect LINE events for one file through ``sys.monitoring``.

    ``sys.monitoring`` rather than ``sys.settrace``: the callback returns
    DISABLE for every code object outside the file, so frames in the
    stdlib and in pyct itself cost nothing after their first line. It
    needs a tool id nobody else holds, taken at start and freed at stop.
    """

    def __init__(self, file: str) -> None:
        self.file = file
        self.seen: set[int] = set()
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
        self.seen.add(line)
        return None


def _free_tool_id() -> int:
    for tool_id in _TOOL_IDS:
        if sys.monitoring.get_tool(tool_id) is None:
            return tool_id
    raise RuntimeError("every sys.monitoring tool id is taken")

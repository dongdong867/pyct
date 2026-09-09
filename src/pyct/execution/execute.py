"""Call the target once and report the lines it ran."""

from __future__ import annotations

import sys
import traceback
import types
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass

from pyct.binding.bind import bind
from pyct.core.branch import _PYCT_DIR, Branch, Downgrade, SinkItem
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
    sink: list[SinkItem] = []
    bound = bind(args, sink)
    tracer = _LineTracer(ctx.file)
    tracer.start()
    try:
        failure = _call(ctx.fn, bound, deadline)
    finally:
        tracer.stop()
    # one sink holds both, in the order they happened; the result reports each in its own
    return ExecutionResult(
        lines=frozenset(tracer.seen),
        branches=tuple(item for item in sink if isinstance(item, Branch)),
        downgrades=tuple(item.name for item in sink if isinstance(item, Downgrade)),
        failure=failure,
    )


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
        return _whose_raise(fn, error)
    return None


def _whose_raise(fn: Callable[..., object], error: Exception) -> Failure:
    """Say whose the raise was.

    An exception raised while the target runs is a **pyct bug** when any frame
    below the target's code object in the traceback lives under pyct's package
    directory; otherwise it is **target raised**. Below means deeper in the
    traceback than the target's own frame, so it covers the calls the target
    made and not the ones that led to it. A pyct bug keeps the whole traceback,
    because the frames are what a person needs to fix pyct.
    """
    if any(tb.tb_frame.f_code.co_filename.startswith(_PYCT_DIR) for tb in _below_target(fn, error)):
        return Failure(
            kind=FailureKind.PYCT_BUG,
            detail=_one_line(error),
            traceback="".join(traceback.format_exception(error)),
        )
    return Failure(kind=FailureKind.TARGET_RAISED, detail=_one_line(error))


def _below_target(fn: Callable[..., object], error: Exception) -> tuple[types.TracebackType, ...]:
    """The traceback entries deeper than the target's own frame, none when it is absent."""
    entries = tuple(_entries(error.__traceback__))
    code = getattr(fn, "__code__", None)
    for index, entry in enumerate(entries):
        if _is_target_frame(entry, code):
            return entries[index + 1 :]
    return ()


def _is_target_frame(entry: types.TracebackType, code: types.CodeType | None) -> bool:
    """The target's own frame runs its code object.

    A callable without one, a ``functools.partial`` say, never gets a frame,
    so the first frame outside pyct stands in for it.
    """
    if code is not None:
        return entry.tb_frame.f_code is code
    return not entry.tb_frame.f_code.co_filename.startswith(_PYCT_DIR)


def _entries(tb: types.TracebackType | None) -> Iterator[types.TracebackType]:
    """The traceback as a sequence, outermost frame first."""
    while tb is not None:
        yield tb
        tb = tb.tb_next


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

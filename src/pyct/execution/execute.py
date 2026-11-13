"""Call the target once and report the lines it ran."""

from __future__ import annotations

import contextlib
import dataclasses
import inspect
import sys
import types
from collections.abc import Callable, Generator, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, field

from pyct.binding.annotations import Check
from pyct.binding.bind import bind
from pyct.binding.builds import Build, BuildError, CallPlan, SelfBuild, plan_call
from pyct.core.foundation.branch import Branch, Fact, PieceRun
from pyct.execution import line_events
from pyct.execution.blame import blame, one_line
from pyct.execution.branch_ways import CodeWays
from pyct.execution.deadline import DeadlineError, close, deadline
from pyct.execution.tally import Tally, Watch, too_long
from pyct.results.coverage import Reach
from pyct.results.failure import Failure, FailureKind
from pyct.results.record import DowngradeCount


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

    ``self_build`` says how each call builds the instance a method runs on, from
    the dict the seed holds under the method's first parameter. A value
    there of any other type is passed as the instance as given. ``home`` is
    the module a bare class name under ``"__class__"`` is read in.
    """

    fn: Callable[..., object]
    file: str
    alone: bool = False
    positional: tuple[inspect.Parameter, ...] = ()
    checks: Mapping[str, Check] = field(default_factory=dict)
    self_build: SelfBuild | None = None
    home: str = ""


@dataclass(frozen=True)
class ExecutionResult:
    """What one call did: the lines it reached, the forks it took, and how it ended.

    On a failure the lines, forks and facts are those reached before it. ``facts`` are what its
    path holds beside the forks, each placed after the forks recorded before it. ``reach`` is
    the functions of the file it entered and the ways their branches went. ``pieces`` are the
    recorded runs of the pieces of the target's code, in the order each ended
    (`pyct.core.entry.pieces`), none when its code has no hooks.
    """

    lines: frozenset[int]
    branches: tuple[Branch, ...]
    downgrades: tuple[DowngradeCount, ...] = ()
    failure: Failure | None = None
    facts: tuple[Fact, ...] = ()
    reach: Reach = field(default_factory=Reach)
    pieces: tuple[PieceRun, ...] = ()


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

    Each object the seed names is built in the call, before the target
    (``plan_call``). One that cannot be planned, its class not loading say,
    ends the input before any line runs, as the target's raise.
    """
    tally = Tally(watch)
    tally.go_live()
    bound = bind(args, tally, ctx.checks, ctx.home)
    try:
        plan = plan_call(bound, ctx.positional, ctx.self_build, ctx.home, ctx.checks)
    except BuildError as error:
        return _unbuilt(tally, error)
    tracer = _LineTracer(ctx.file, tally)
    tracer.start()
    block = deadline(until)
    try:
        ending = _call(ctx, plan, block)
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
        reach=tally.reach(),
        pieces=tuple(tally.pieces),
    )


@dataclass(frozen=True)
class _Ending:
    """How the call ended: the raise that ended it, if any, and whether the target was reached.

    ``called`` says whether the target was reached: a target that runs in
    C leaves no frame, so blame cannot read that from the traceback.
    ``building`` is the object whose constructor raised, for a raise while
    the objects the call passes were built.
    """

    error: BaseException | None
    called: bool
    building: Build | None = None


def _unbuilt(tally: Tally, error: BuildError) -> ExecutionResult:
    """An input none of whose objects was built: one of them cannot be, its class not loading
    say. It fails as the target's raise, with the object's place, and runs nothing."""
    tally.seal()
    detail = f"building {error.place}: {error.reason}"
    return ExecutionResult(
        lines=frozenset(),
        branches=(),
        failure=Failure(kind=FailureKind.TARGET_RAISED, detail=detail),
    )


def _call(ctx: ExecutionContext, plan: CallPlan, block: AbstractContextManager[None]) -> _Ending:
    """Call the target inside the deadline's ``block`` and keep how it ended, for ``_failure``
    to write once the sink is read.

    Each object the call passes is built in this frame first, innermost
    first, inside the block, so a constructor runs under the tracer and the
    deadline as the target does, and blame reads its frames as a class
    target's. Each object goes into its slot by item assignment, which runs
    no Python frame. A positional-only parameter is passed by position.
    """
    called = False
    building = None
    caught = BaseException if ctx.alone else (DeadlineError, SystemExit, Exception)
    try:
        # the limit goes back after the block, where no alarm of the call's can land
        with _room_below(_depth(sys._getframe()) - 1), block:
            called = True
            try:
                for building in plan.builds:
                    made = building.cls(*building.positional, **building.keywords)
                    building.into[building.slot] = made  # pyrefly: ignore[unsupported-operation]
                    del made
                building = None
                ctx.fn(*plan.positional, **plan.keywords)
            finally:
                # dropped inside the block, as plain Python drops each object once the call
                # returns, so a `__del__` runs under the deadline
                plan.drop()
    except caught as error:
        return _Ending(error=error, called=called, building=building)
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
    """The failure a raise ended the call with, or None for a call that returned.

    A raise while an object the call passes was built is blamed against its
    class, and the target's raise or ``SystemExit`` names the object's place
    first.
    """
    error = ending.error
    # the alarm can land in pyct's own frames too, so the kind is by type, before the rest
    if isinstance(error, DeadlineError):
        # only a fired alarm reaches here, and those tests run without coverage
        return Failure(kind=FailureKind.TIMEOUT, detail="deadline passed")  # pragma: no cover
    if error is None:
        return None
    if isinstance(error, SystemExit):
        failure = Failure(kind=FailureKind.SYSTEM_EXIT, detail=one_line(error))
    else:
        blamed = fn if ending.building is None else ending.building.cls
        failure = blame(blamed, error, called=ending.called)
    if ending.building is None or failure.kind is FailureKind.PYCT_BUG:
        return failure
    return dataclasses.replace(
        failure, detail=f"building {ending.building.place}: {failure.detail}"
    )


class _LineTracer:
    """Collect LINE and BRANCH events for one file through ``sys.monitoring``.

    ``sys.monitoring`` rather than ``sys.settrace``: the callback returns
    DISABLE for every code object outside the file, so frames in the
    stdlib and in pyct itself cost nothing after their first line. It
    needs a tool id nobody else holds, taken at start and freed at stop
    (``execution.line_events``).

    A code object of the file is entered when one of its lines is first
    seen, or when its first branch event comes: its bytecode is read then,
    once (``CodeWays``), and each branch event in it is read through that.
    """

    def __init__(self, file: str, tally: Tally) -> None:
        self.file = file
        self.tally = tally
        self.seen = tally.lines
        self.tool_id: int | None = None
        # each code object entered, by id, kept beside its ways so the id stays its own
        self.entered: dict[int, tuple[types.CodeType, CodeWays]] = {}
        # each branch event already read, by its code's id, test and target: a loop's test
        # reports the same few on every pass, and one seen before costs one lookup
        self.read: set[tuple[int, int, int]] = set()

    def start(self) -> None:
        self.tool_id = line_events.listen(self._on_line, self._on_branch)

    def stop(self) -> None:
        if self.tool_id is None:
            return
        line_events.stop(self.tool_id)
        self.tool_id = None

    def _on_line(self, code: types.CodeType, line: int) -> object:
        if code.co_filename != self.file:
            return sys.monitoring.DISABLE
        # a line seen before costs one set lookup, as it did before the tally
        if line not in self.seen:
            self._ways(code)
            self.tally.line(line)
        return None

    def _on_branch(self, code: types.CodeType, test: int, target: int) -> object:
        key = (id(code), test, target)
        if key in self.read:
            return None
        if code.co_filename != self.file:
            return sys.monitoring.DISABLE
        self.read.add(key)
        went = self._ways(code).way(test, target)
        if went is not None:
            self.tally.went(*went)
        return None

    def _ways(self, code: types.CodeType) -> CodeWays:
        """The code object's ways, read and handed to the tally the first time it is met."""
        known = self.entered.get(id(code))
        if known is not None:
            return known[1]
        ways = CodeWays(code)
        self.entered[id(code)] = (code, ways)
        self.tally.enter(ways.lines, ways.branches)
        return ways

"""Run one target with the seed, then with an input per fork the seed and its inputs left open."""

from __future__ import annotations

import platform
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import assert_never

from pyct.binding.bind import leaves
from pyct.binding.model import apply
from pyct.branches.compare import compare
from pyct.branches.plan import Plan
from pyct.branches.tree import Tree
from pyct.config.budget import Budget
from pyct.config.limits import Limits
from pyct.config.solver_timeout import DEFAULT_SECONDS
from pyct.execution.execute import ExecutionResult
from pyct.results.coverage import Coverage, Scope, no_gain
from pyct.results.record import (
    Environment,
    InputRecord,
    Miss,
    MissWhy,
    RunResult,
    Source,
    Stop,
    StopKind,
)
from pyct.run.isolation import Call, Inputs, Isolation
from pyct.run.process import InputStartError
from pyct.run.target import Target
from pyct.solver.answer import Error, Sat, Timeout, Unknown, Unsat
from pyct.solver.cvc5 import solve
from pyct.solver.locate import locate, version

_NO_LIMITS = Limits()

# what a caller does with an input the moment it is finished
type Report = Callable[[InputRecord, Coverage], None]

# what a caller does with a fork the solver could not flip, the moment the answer comes in
type Missed = Callable[[Miss], None]


@dataclass(frozen=True)
class Tell:
    """What a caller does with each fact of the run the moment it happens.

    ``report`` takes each finished input with the lines that input alone
    covered; ``missed`` takes each fork the solver gave no input for. One
    object rather than a keyword per kind of fact, so ``run()`` and the loop
    keep to five parameters: a later kind of fact widens this instead of
    their signatures. A Tell with nothing set hands nothing out.
    """

    report: Report | None = None
    missed: Missed | None = None


_TELL_NOTHING = Tell()


@dataclass(frozen=True)
class _Told:
    """The caller's Tell, with the scope each reported input's coverage is measured in."""

    scope: Scope
    tell: Tell

    def record(self, record: InputRecord) -> None:
        """Hand out a finished input, with the lines that one input covered."""
        if self.tell.report is not None:
            self.tell.report(record, Coverage.of(self.scope, record.covered_lines))

    def miss(self, miss: Miss) -> None:
        """Hand out a fork the solver gave no input for."""
        if self.tell.missed is not None:
            self.tell.missed(miss)


@dataclass(frozen=True)
class Bounds:
    """When the loop must stop asking, and how long one solve may take.

    The budget becomes an instant here, because the clock starts when the call
    does, not when the person typed the seconds. The solver timeout stays
    seconds, because each solve starts its own clock. All in one value, so the
    loop and each pass keep to five parameters.
    """

    until: float | None = None
    plateau: int | None = None
    solver_timeout: float = DEFAULT_SECONDS

    @classmethod
    def of(cls, limits: Limits) -> Bounds:
        return cls(
            until=_deadline_for(limits.budget),
            plateau=limits.plateau.inputs,
            solver_timeout=limits.solver_timeout.seconds,
        )


@dataclass(frozen=True)
class Attempt:
    """What one pass of the loop produced: an input, or a miss, or the reason to stop."""

    stop: Stop | None = None
    record: InputRecord | None = None
    miss: Miss | None = None


@dataclass(frozen=True)
class Loop:
    """The inputs that ran, the seed's first, what the solver missed, and why they stopped."""

    records: tuple[InputRecord, ...]
    misses: tuple[Miss, ...]
    stop: Stop


def run(
    target: Target,
    seed: Mapping[str, object],
    *,
    limits: Limits = _NO_LIMITS,
    isolation: Isolation = Isolation.AUTO,
    tell: Tell = _TELL_NOTHING,
) -> RunResult:
    """Call the target with the seed, then with an input per fork left open.

    ``isolation`` says where each input runs: by default in a process of its
    own, and ``Isolation.IN_PROCESS`` runs every input in the caller's
    process (see ``Isolation``). Each input goes to
    ``tell.report`` as it finishes, with the coverage of that input alone, so
    an input that hangs never hides the lines of the ones before it. Each
    fork the solver could not flip goes to ``tell.missed`` the same way, so a
    reader sees it when its answer comes in, before the next input's trace.
    """
    scope = Scope.of_module(target.file)
    inputs = Inputs(target, isolation)
    # before the deadline starts: the probe is the run's setup, not its time
    cvc5 = version(locate())
    bounds = Bounds.of(limits)
    looped = _inputs(inputs, seed, bounds, _Told(scope=scope, tell=tell))
    covered = frozenset[int]().union(*(record.covered_lines for record in looped.records))
    return RunResult(
        entry=target.spec,
        records=looped.records,
        coverage=Coverage.of(scope, covered),
        stopped=looped.stop,
        environment=_environment(cvc5, inputs.isolated),
        misses=looped.misses,
    )


def _inputs(call: Call, seed: Mapping[str, object], bounds: Bounds, told: _Told) -> Loop:
    """The seed and every input after it, what the solver missed, and why they stopped.

    A seed whose process cannot start stops the run before any input.
    """
    try:
        seeded = _record_of(seed, call(seed, bounds.until))
    except InputStartError as error:
        return Loop((), (), _could_not_start(error))
    told.record(seeded)
    tree = Tree()
    tree.add(seeded.forks)
    looped = _loop(call, seeded, tree, bounds, told)
    return Loop((seeded, *looped.records), looped.misses, looped.stop)


def _could_not_start(error: InputStartError) -> Stop:
    """The stop for an input pyct could not start a process for, with the system's reason."""
    return Stop(StopKind.COULD_NOT_START, str(error))


def _environment(cvc5: str | None, isolated: bool) -> Environment:
    """What the run ran in: the version the cvc5 the solver used gave, and where inputs ran.

    A cvc5 that will not say its version leaves the version out; the run is
    the same run either way. ``isolated`` is known only once the inputs ran,
    since a run can move to pyct's own process part way.
    """
    return Environment(
        python=platform.python_version(),
        cvc5=cvc5,
        platform=platform.platform(),
        isolated=isolated,
    )


def _loop(
    call: Call,
    seeded: InputRecord,
    tree: Tree,
    bounds: Bounds,
    told: _Told,
) -> Loop:
    """Pick a fork, run what the solver answers for it, until a pass says to stop.

    Every input's forks join the tree the next pick draws from, so an input
    that raised or left its plan feeds the loop like any other. A miss is
    kept, handed out before the next pick, and the loop goes on: the fork is
    spent either way.

    ``covered`` is the lines of each input that ran, in run order, the seed's
    first; a miss ran no input and adds none. The scope is applied here
    because a record carries the tracer's raw lines.
    """
    records: list[InputRecord] = []
    misses: list[Miss] = []
    covered = [seeded.covered_lines & told.scope.lines]
    while True:
        attempt = _attempt(call, seeded.args, tree, bounds, covered)
        if attempt.stop is not None:
            return Loop(tuple(records), tuple(misses), attempt.stop)
        if attempt.miss is not None:
            misses.append(attempt.miss)
            told.miss(attempt.miss)
        if attempt.record is not None:
            records.append(attempt.record)
            covered.append(attempt.record.covered_lines & told.scope.lines)
            tree.add(attempt.record.forks)
            told.record(attempt.record)


def _attempt(
    call: Call,
    seed: Mapping[str, object],
    tree: Tree,
    bounds: Bounds,
    covered: Sequence[frozenset[int]],
) -> Attempt:
    """One pass of the loop: the clock, a fork to aim at, the plateau, the solver, the input.

    The three reasons come in the README's order. The budget first, because a
    run that spent it has paths cut short, so ``no fork to flip`` would claim
    more than the run knows; the clock alone decides it, because the alarm
    fires only at the deadline, so an input's timeout failure would say the
    same thing twice, and a target that swallows the alarm leaves no failure
    for a second rule to read. Then the tree, then the plateau, so a run that
    emptied the tree says so even when the plateau also holds.

    Each solve gets the solver timeout, or what is left of the budget when
    that is less, so the budget still bounds the solver. A solver that
    crashed ends the run as a failure, and so does an input pyct could not
    start a process for. Any other answer is an input to run, or a miss on
    that fork.
    """
    left = _seconds_left(bounds.until)
    # a deadline that has passed is no time at all; cvc5 reads --tlimit-per=0 as no limit
    if left is not None and left <= 0:
        return Attempt(stop=Stop(StopKind.BUDGET))
    wanted = tree.next()
    if wanted is None:
        return Attempt(stop=Stop(StopKind.NO_FORK))
    if bounds.plateau is not None and no_gain(covered, bounds.plateau):
        return Attempt(stop=Stop(StopKind.NO_GAIN, plateau=bounds.plateau))
    answer = solve(wanted.prefix, leaves(seed), _solve_limit(bounds, left))
    if isinstance(answer, Error):
        return Attempt(stop=Stop(StopKind.SOLVER_FAILED, answer.detail))
    if not isinstance(answer, Sat):
        return Attempt(miss=Miss(wanted.aim.site, _why(answer)))
    args = apply(seed, answer.model)
    try:
        return Attempt(record=_record_of(args, call(args, bounds.until), wanted))
    except InputStartError as error:
        return Attempt(stop=_could_not_start(error))


def _why(answer: Unsat | Unknown | Timeout) -> MissWhy:
    """What the solver said about a fork it gave no input for, in the run's own words.

    A match rather than a table, so a new answer fails the type check
    instead of a run.
    """
    match answer:
        case Unsat():
            return MissWhy.UNSAT
        case Unknown():
            return MissWhy.UNKNOWN
        case Timeout():
            return MissWhy.TIMEOUT
        case _:
            assert_never(answer)


def _record_of(
    args: Mapping[str, object],
    executed: ExecutionResult,
    wanted: Plan | None = None,
) -> InputRecord:
    """What one input did. A plan makes it the solver's, aimed and read against that plan.

    The lines are the tracer's, unmeasured: Coverage.of is where the scope is applied.
    """
    return InputRecord(
        args=args,
        forks=executed.branches,
        covered_lines=executed.lines,
        failure=executed.failure,
        downgrades=executed.downgrades,
        source=Source.SEED if wanted is None else Source.SOLVER,
        aim=None if wanted is None else wanted.aim,
        mismatch_at=None if wanted is None else compare(wanted.prefix, executed.branches),
    )


def _deadline_for(budget: Budget) -> float | None:
    """The monotonic instant the call must end by. No seconds, no deadline."""
    return None if budget.seconds is None else time.monotonic() + budget.seconds


def _seconds_left(until: float | None) -> float | None:
    """The seconds the deadline still allows. No deadline, no limit."""
    return None if until is None else until - time.monotonic()


def _solve_limit(bounds: Bounds, left: float | None) -> float:
    """The seconds one solve gets: the solver timeout, or ``left`` when the budget has less.

    ``left`` is read once, before the budget check, so a solve always gets
    the same time the check found above zero.
    """
    return bounds.solver_timeout if left is None else min(bounds.solver_timeout, left)

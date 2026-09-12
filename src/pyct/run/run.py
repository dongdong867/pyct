"""Run one target with the seed, then with the input the solver answers."""

import time
from collections.abc import Callable, Mapping

from pyct.binding.bind import leaves
from pyct.binding.model import apply
from pyct.branches.compare import compare
from pyct.branches.plan import Plan, plan
from pyct.config.budget import Budget
from pyct.execution.execute import ExecutionContext, ExecutionResult, execute
from pyct.results.coverage import Coverage, Scope
from pyct.results.record import InputRecord, RunResult, Source
from pyct.run.target import Target
from pyct.solver.answer import Sat
from pyct.solver.cvc5 import solve

_NO_BUDGET = Budget()

# what a caller does with an input the moment it is finished
type Report = Callable[[InputRecord, Coverage], None]


def run(
    target: Target,
    seed: Mapping[str, object],
    *,
    budget: Budget = _NO_BUDGET,
    report: Report | None = None,
) -> RunResult:
    """Call the target with the seed, then with the other side of its last fork.

    The budget becomes a deadline here, because the clock starts when the
    call does, not when the person typed the seconds. Each input goes to
    ``report`` as it finishes, with the coverage of that input alone, so a
    second input that hangs never hides the first one's line.
    """
    scope = Scope.of_module(target.file)
    ctx = ExecutionContext(fn=target.fn, file=target.file)
    until = _deadline_for(budget)
    records = [_record_of(seed, execute(ctx, seed, until), scope)]
    _tell(report, records[0], scope)
    second = _second_input(ctx, scope, seed, records[0], until)
    if second is not None:
        records.append(second)
        _tell(report, second, scope)
    covered = frozenset[int]().union(*(record.covered_lines for record in records))
    return RunResult(
        entry=target.spec, records=tuple(records), coverage=Coverage.of(scope, covered)
    )


def _second_input(
    ctx: ExecutionContext,
    scope: Scope,
    seed: Mapping[str, object],
    first: InputRecord,
    until: float | None,
) -> InputRecord | None:
    """The input that takes the other side of the seed's last fork, if there is one.

    Nothing to flip, no time to ask, or no input that takes the path: the
    run ends after the seed. Saying which of the three is the next story's.
    """
    wanted = plan(first.forks)
    if wanted is None:
        return None
    timeout = _seconds_left(until)
    # a deadline that has passed is no time at all; cvc5 reads --tlimit=0 as no limit
    if timeout is not None and timeout <= 0:
        return None
    answer = solve(wanted.prefix, leaves(seed), timeout)
    if not isinstance(answer, Sat):
        return None
    args = apply(seed, answer.model)
    return _record_of(args, execute(ctx, args, until), scope, wanted)


def _record_of(
    args: Mapping[str, object],
    executed: ExecutionResult,
    scope: Scope,
    wanted: Plan | None = None,
) -> InputRecord:
    """What one input did. A plan makes it the solver's, aimed and read against that plan."""
    return InputRecord(
        args=args,
        forks=executed.branches,
        covered_lines=executed.lines & scope.lines,
        failure=executed.failure,
        downgrades=executed.downgrades,
        source=Source.SEED if wanted is None else Source.SOLVER,
        aim=None if wanted is None else wanted.aim,
        mismatch_at=None if wanted is None else compare(wanted.prefix, executed.branches),
    )


def _tell(report: Report | None, record: InputRecord, scope: Scope) -> None:
    """Hand a finished input to the caller, with the lines that one input covered."""
    if report is not None:
        report(record, Coverage.of(scope, record.covered_lines))


def _deadline_for(budget: Budget) -> float | None:
    """The monotonic instant the call must end by. No seconds, no deadline."""
    return None if budget.seconds is None else time.monotonic() + budget.seconds


def _seconds_left(until: float | None) -> float | None:
    """The seconds the deadline still allows. No deadline, no limit."""
    return None if until is None else until - time.monotonic()

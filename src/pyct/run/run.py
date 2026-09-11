"""Run one target once with one seed."""

import time
from collections.abc import Mapping

from pyct.config.budget import Budget
from pyct.execution.execute import ExecutionContext, execute
from pyct.results.coverage import Coverage, Scope
from pyct.results.record import InputRecord, RunResult
from pyct.run.target import Target

_NO_BUDGET = Budget()


def run(target: Target, seed: Mapping[str, object], *, budget: Budget = _NO_BUDGET) -> RunResult:
    """Call the target with the seed as keyword arguments and measure it against its module.

    The budget becomes a deadline here, because the clock starts when the
    call does, not when the person typed the seconds.
    """
    scope = Scope.of_module(target.file)
    ctx = ExecutionContext(fn=target.fn, file=target.file)
    executed = execute(ctx, seed, _deadline_for(budget))
    coverage = Coverage.of(scope, executed.lines)
    record = InputRecord(
        args=seed,
        forks=executed.branches,
        covered_lines=coverage.covered[scope.file],
        failure=executed.failure,
        downgrades=executed.downgrades,
    )
    return RunResult(entry=target.spec, records=(record,), coverage=coverage)


def _deadline_for(budget: Budget) -> float | None:
    """The monotonic instant the call must end by. No seconds, no deadline."""
    return None if budget.seconds is None else time.monotonic() + budget.seconds

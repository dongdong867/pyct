"""What one input did, as its record, and what the solver said of a fork it gave no input for."""

from __future__ import annotations

from collections.abc import Mapping
from typing import assert_never

from pyct.branches.compare import compare
from pyct.branches.plan import Plan
from pyct.execution.execute import ExecutionResult
from pyct.results.record import InputRecord, MissWhy, Source
from pyct.solver.answer import Timeout, Unknown, Unsat


def miss_why(answer: Unsat | Unknown | Timeout) -> MissWhy:
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


def record_of(
    args: Mapping[str, object],
    executed: ExecutionResult,
    wanted: Plan | None = None,
    seconds: float | None = None,
) -> InputRecord:
    """What one input did. A plan makes it the solver's, aimed and read against that plan, and
    ``seconds`` is how long the ask for it took.

    The lines are the tracer's, unmeasured: Coverage.of is where the scope is applied.
    """
    return InputRecord(
        args=args,
        forks=executed.branches,
        facts=executed.facts,
        covered_lines=executed.lines,
        failure=executed.failure,
        downgrades=executed.downgrades,
        source=Source.SEED if wanted is None else Source.SOLVER,
        aim=None if wanted is None else wanted.aim,
        mismatch_at=None if wanted is None else compare(wanted.prefix, executed.branches),
        reach=executed.reach,
        solver_seconds=seconds,
    )

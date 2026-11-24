"""What one input did, as its record, and the answer a fork's ask ended in when it gave no input."""

from __future__ import annotations

from collections.abc import Mapping
from typing import assert_never

from pyct.branches.compare import compare
from pyct.branches.plan import Plan
from pyct.execution.execute import ExecutionResult
from pyct.results.record import InputRecord, MissWhy, Source
from pyct.solver.answer import Timeout, Unknown, Unsat


def miss_why(answer: Unsat | Unknown | Timeout) -> MissWhy:
    """The answer a fork's ask ended in when it gave no input, in the run's own words.

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
        pieces=executed.pieces,
        drops=executed.drops,
        losses=executed.losses,
    )


def source_of(wanted: Plan, source: Source) -> Source:
    """Where the input a pass's answer gave came from: ``summary`` for the solver's own answer
    when the fork aimed at is a formula's, one a loop's formula recorded or one that reads a
    value a formula gave (``Branch.summary``), else ``source``, a kept rewrite's included."""
    if source is Source.SOLVER and wanted.prefix[-1].summary:
        return Source.SUMMARY
    return source

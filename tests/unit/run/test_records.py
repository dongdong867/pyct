"""An input's record holds what its call did, the recorded runs of its loss sites among it, and a
pass's input takes the source of the fork it was aimed at."""

import pytest

from pyct.branches.plan import plan
from pyct.core.foundation.branch import Branch, Changed, GoingIn, LossKind, LossRun, Site
from pyct.execution.execute import ExecutionResult
from pyct.results.record import InputRecord, Source
from pyct.run.records import record_of, source_of

RUN = LossRun(
    Site(file="m.py", line=3, col=4),
    "__pow__",
    LossKind.OPERATION,
    (GoingIn("arg1", "2", tracked=True),),
    (Changed("answer", "2"),),
)


def test_a_record_holds_the_recorded_runs_of_its_call_s_loss_sites() -> None:
    executed = ExecutionResult(lines=frozenset({3}), branches=(), losses=(RUN,))

    record = record_of({"n": 2}, executed)

    assert record.losses == (RUN,)
    assert InputRecord(args={}, forks=(), covered_lines=frozenset()).losses == ()


def aimed(*, summary: bool) -> object:
    forks = (
        Branch(["<", "x", 3], True, Site("m.py", 2, 3)),
        Branch([">", "t", 3], False, Site("m.py", 5, 3), summary=summary),
    )
    return plan(forks)


@pytest.mark.parametrize(
    ("summary", "given", "source"),
    [
        (True, Source.SOLVER, Source.SUMMARY),
        (False, Source.SOLVER, Source.SOLVER),
        (True, Source.REWRITE, Source.REWRITE),
    ],
)
def test_a_pass_s_input_is_summary_s_when_the_solver_aimed_at_a_marked_fork(
    summary: bool, given: Source, source: Source
) -> None:
    wanted = aimed(summary=summary)
    assert wanted is not None

    assert source_of(wanted, given) is source  # type: ignore[arg-type]

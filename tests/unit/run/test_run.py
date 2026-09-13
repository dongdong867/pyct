import time
from pathlib import Path

import pytest

from pyct.config.budget import Budget
from pyct.core.branch import Branch, Site
from pyct.execution.execute import ExecutionContext
from pyct.results.coverage import Coverage
from pyct.results.failure import Failure, FailureKind
from pyct.results.record import Aim, InputRecord, Source, StopKind
from pyct.run.run import _second_input, run
from pyct.run.target import load_target

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = str(REPO_ROOT / "targets" / "trace" / "uncalled_helper.py")
ONE_CHECK = str(REPO_ROOT / "targets" / "flip" / "one_check.py")
NESTED_CHECKS = str(REPO_ROOT / "targets" / "flip" / "nested_checks.py")
OTHER_SIDE_LONGER = str(REPO_ROOT / "targets" / "flip" / "other_side_longer.py")


def argument(record: InputRecord, name: str) -> int:
    """One int argument off a record, narrowed so the comparison means something."""
    value = record.args[name]
    assert isinstance(value, int), record.args
    return value


def test_run_records_the_seed_and_measures_it_against_the_module() -> None:
    target = load_target("targets.trace.uncalled_helper::classify")

    result = run(target, {"x": 1})

    assert result.entry == "targets.trace.uncalled_helper::classify"
    assert result.records[0].args == {"x": 1}
    assert result.records[0].covered_lines == frozenset({5, 6})
    # the run's coverage is every input's, the other side of the fork included
    assert result.coverage.covered == {FIXTURE: frozenset({5, 6, 7})}
    assert result.coverage.total == {FIXTURE: 7}


def test_run_records_the_forks_the_seed_took() -> None:
    target = load_target("targets.trace.uncalled_helper::classify")

    result = run(target, {"x": 3})

    assert result.records[0].forks == (
        Branch(
            expression=["<", "x", 10],
            taken=True,
            site=Site(file=FIXTURE, line=5, col=7),
        ),
    )


def test_run_records_how_the_seed_ended() -> None:
    target = load_target("targets.trace.raises::explode")

    result = run(target, {"x": 3})

    assert result.records[0].failure == Failure(
        kind=FailureKind.TARGET_RAISED, detail="ValueError: too small"
    )
    assert result.records[0].covered_lines == frozenset({2, 3})


def test_run_reports_a_timeout_when_the_budget_runs_out() -> None:
    target = load_target("targets.trace.never_returns::spin")

    result = run(target, {"x": 1}, budget=Budget(seconds=0.05))

    # the seed forked nowhere, so there is nothing to ask the solver about
    assert len(result.records) == 1
    assert result.records[0].failure == Failure(kind=FailureKind.TIMEOUT, detail="deadline passed")
    assert result.records[0].covered_lines == frozenset({2, 3, 4})


def test_a_deadline_that_has_passed_leaves_the_solver_unasked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = load_target("targets.flip.one_check::classify")
    seed = {"x": 3}
    forked = run(target, seed).records[0]
    # no cvc5 on the PATH: asking would raise rather than answer
    monkeypatch.setenv("PATH", str(tmp_path))
    ctx = ExecutionContext(fn=target.fn, file=target.file)

    flip = _second_input(ctx, seed, forked, time.monotonic() - 1)

    assert flip.record is None
    assert flip.stop.kind is StopKind.BUDGET


def test_run_solves_for_the_other_side_of_the_seeds_fork() -> None:
    target = load_target("targets.flip.one_check::classify")

    result = run(target, {"x": 3})

    assert len(result.records) == 2
    solved = result.records[1]
    assert solved.source is Source.SOLVER
    assert solved.aim == Aim(site=Site(file=ONE_CHECK, line=2, col=7), position=0)
    assert solved.mismatch_at is None
    assert solved.forks == (
        Branch(expression=["<", "x", 10], taken=False, site=Site(file=ONE_CHECK, line=2, col=7)),
    )
    assert argument(solved, "x") >= 10


def test_run_keeps_the_earlier_forks_and_flips_the_last() -> None:
    target = load_target("targets.flip.nested_checks::bucket")

    result = run(target, {"x": 3})

    solved = result.records[1]
    assert solved.forks == (
        Branch(
            expression=["<", "x", 100], taken=True, site=Site(file=NESTED_CHECKS, line=2, col=7)
        ),
        Branch(
            expression=["<", "x", 10], taken=False, site=Site(file=NESTED_CHECKS, line=3, col=11)
        ),
    )
    assert solved.aim == Aim(site=Site(file=NESTED_CHECKS, line=3, col=11), position=1)
    assert 10 <= argument(solved, "x") < 100


def test_run_keeps_the_arguments_the_fork_does_not_name() -> None:
    target = load_target("targets.flip.two_args::pick")

    result = run(target, {"x": 3, "y": 7})

    solved = result.records[1]
    assert argument(solved, "x") >= 10
    assert argument(solved, "y") == 7


def test_run_counts_every_input_in_the_coverage() -> None:
    target = load_target("targets.flip.other_side_longer::grade")

    result = run(target, {"x": 3})

    seed, solved = result.records
    assert seed.covered_lines == frozenset({2, 3})
    assert solved.covered_lines == frozenset({2, 4, 5, 6})
    assert result.coverage.covered == {OTHER_SIDE_LONGER: seed.covered_lines | solved.covered_lines}
    assert result.coverage.total == {OTHER_SIDE_LONGER: 6}


def test_run_reports_each_input_as_it_finishes() -> None:
    target = load_target("targets.flip.one_check::classify")
    reported: list[tuple[InputRecord, Coverage]] = []

    def remember(record: InputRecord, coverage: Coverage) -> None:
        reported.append((record, coverage))

    result = run(target, {"x": 3}, report=remember)

    assert [record for record, _ in reported] == list(result.records)
    # the seed's coverage is the seed's own lines, not what the run has covered so far
    assert reported[0][1].covered == {ONE_CHECK: frozenset({2, 3})}
    assert reported[0][1].total == {ONE_CHECK: 4}


def test_run_stops_after_a_seed_that_forked_nowhere() -> None:
    target = load_target("targets.flip.no_check::echo")

    result = run(target, {"x": 3})

    assert len(result.records) == 1
    assert result.records[0].source is Source.SEED
    assert result.stopped.kind is StopKind.NO_FORK
    assert result.stopped.detail is None
    assert result.misses == ()


def test_run_stops_after_one_attempt_when_the_solver_gave_an_input() -> None:
    target = load_target("targets.flip.one_check::classify")

    result = run(target, {"x": 3})

    assert len(result.records) == 2
    assert result.stopped.kind is StopKind.ONE_ATTEMPT
    assert result.misses == ()


def test_run_stops_on_the_budget_when_the_seed_forked_and_then_spent_it() -> None:
    target = load_target("targets.flip.spins_after_a_check::spin")

    result = run(target, {"x": 3}, budget=Budget(seconds=0.05))

    assert len(result.records) == 1
    assert result.records[0].failure == Failure(kind=FailureKind.TIMEOUT, detail="deadline passed")
    assert result.stopped.kind is StopKind.BUDGET

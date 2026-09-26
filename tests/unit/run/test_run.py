import functools
import platform
import time
from pathlib import Path

import pytest

from pyct.branches.tree import Tree
from pyct.config.budget import Budget
from pyct.config.limits import Limits
from pyct.config.plateau import Plateau
from pyct.config.solver_timeout import SolverTimeout
from pyct.core.branch import Branch, Site
from pyct.execution.execute import ExecutionContext, execute
from pyct.results.coverage import Coverage
from pyct.results.failure import Failure, FailureKind
from pyct.results.record import Aim, InputRecord, Miss, MissWhy, Source, Stop, StopKind
from pyct.run.run import Bounds, Tell, _attempt, run
from pyct.run.target import load_target
from pyct.solver.answer import Answer, Timeout, Unknown

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = str(REPO_ROOT / "targets" / "trace" / "uncalled_helper.py")
ONE_CHECK = str(REPO_ROOT / "targets" / "flip" / "one_check.py")
NESTED_CHECKS = str(REPO_ROOT / "targets" / "flip" / "nested_checks.py")
OTHER_SIDE_LONGER = str(REPO_ROOT / "targets" / "flip" / "other_side_longer.py")
IMPLIED_CHECK = str(REPO_ROOT / "targets" / "flip" / "implied_check.py")


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


@pytest.mark.usefixtures("deadline_fires_in_a_child")
def test_run_reports_a_timeout_when_the_budget_runs_out() -> None:
    target = load_target("targets.trace.never_returns::spin")

    result = run(target, {"x": 1}, limits=Limits(budget=Budget(seconds=0.05)))

    assert len(result.records) == 1
    assert result.records[0].failure == Failure(kind=FailureKind.TIMEOUT, detail="deadline passed")
    assert result.records[0].covered_lines == frozenset({2, 3, 4})
    # both reasons hold; the spent budget is the one the run names
    assert result.stopped.kind is StopKind.BUDGET


def test_a_deadline_that_has_passed_leaves_the_solver_unasked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = load_target("targets.flip.one_check::classify")
    seed = {"x": 3}
    tree = Tree()
    tree.add(run(target, seed).records[0].forks)
    # no cvc5 on the PATH: asking would raise rather than answer
    monkeypatch.setenv("PATH", str(tmp_path))
    call = functools.partial(execute, ExecutionContext(fn=target.fn, file=target.file))

    attempt = _attempt(call, seed, tree, Bounds(until=time.monotonic() - 1), ())

    assert attempt.record is None
    assert attempt.stop == Stop(kind=StopKind.BUDGET)


def limits_given(monkeypatch: pytest.MonkeyPatch, limits: Limits) -> list[float]:
    """The time limit each solve got, over a run whose one fork the solver misses."""
    given: list[float] = []

    def unknown(prefix: object, names: object, timeout: float) -> Answer:
        given.append(timeout)
        return Unknown()

    monkeypatch.setattr("pyct.run.run.solve", unknown)
    run(load_target("targets.flip.one_check::classify"), {"x": 3}, limits=limits)
    return given


def test_a_run_with_no_limits_gives_each_solve_ten_seconds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert limits_given(monkeypatch, Limits()) == [10.0]


def test_each_solve_gets_the_solver_timeout_when_there_is_no_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limits = Limits(solver_timeout=SolverTimeout(seconds=2.5))

    assert limits_given(monkeypatch, limits) == [2.5]


def test_a_solve_gets_the_solver_timeout_when_the_budget_has_more_left(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limits = Limits(budget=Budget(seconds=30.0), solver_timeout=SolverTimeout(seconds=1.0))

    assert limits_given(monkeypatch, limits) == [1.0]


def test_a_solve_gets_what_is_left_of_the_budget_when_that_is_shorter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limits = Limits(budget=Budget(seconds=5.0), solver_timeout=SolverTimeout(seconds=30.0))

    (given,) = limits_given(monkeypatch, limits)

    # the seed ran first, so some of the budget is gone, and the rest is still above zero
    assert 0 < given <= 5.0


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


def test_run_follows_a_str_through_a_deep_copy() -> None:
    target = load_target("targets.strs.deep_copy::check")

    result = run(target, {"name": "x"})

    # the copy is the tracked str itself, so the compare after it is a fork the solver flips
    assert result.records[0].failure is None
    assert [
        (record.args, [(fork.expression, fork.taken) for fork in record.forks])
        for record in result.records
    ] == [
        ({"name": "x"}, [(["==", "name", "'admin'"], False)]),
        ({"name": "admin"}, [(["==", "name", "'admin'"], True)]),
    ]


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

    result = run(target, {"x": 3}, tell=Tell(report=remember))

    assert [record for record, _ in reported] == list(result.records)
    # the seed's coverage is the seed's own lines, not what the run has covered so far
    assert reported[0][1].covered == {ONE_CHECK: frozenset({2, 3})}
    assert reported[0][1].total == {ONE_CHECK: 4}


def test_run_hands_out_a_miss_before_the_input_solved_next() -> None:
    target = load_target("targets.flip.implied_check::narrow")
    told: list[InputRecord | Miss] = []

    result = run(
        target,
        {"x": 3},
        tell=Tell(
            report=lambda record, _: told.append(record),
            missed=lambda miss: told.append(miss),
        ),
    )

    # the inner fork is unsat and the outer one sat, so the miss falls between the two inputs
    seed, solved = result.records
    assert told == [seed, *result.misses, solved]


def test_run_stops_after_a_seed_that_forked_nowhere() -> None:
    target = load_target("targets.flip.no_check::echo")

    result = run(target, {"x": 3})

    assert len(result.records) == 1
    assert result.records[0].source is Source.SEED
    assert result.stopped.kind is StopKind.NO_FORK
    assert result.stopped.detail is None
    assert result.misses == ()


def test_run_stops_when_every_fork_has_been_aimed_at() -> None:
    target = load_target("targets.flip.one_check::classify")

    result = run(target, {"x": 3})

    # the one fork went both ways, so the second input leaves nothing to pick
    assert len(result.records) == 2
    assert result.stopped.kind is StopKind.NO_FORK
    assert result.misses == ()


def test_run_keeps_picking_until_the_tree_is_empty() -> None:
    target = load_target("targets.flip.nested_checks::bucket")

    result = run(target, {"x": 3})

    # the seed takes both checks; the other side of each is an input of its own
    assert [record.source for record in result.records] == [
        Source.SEED,
        Source.SOLVER,
        Source.SOLVER,
    ]
    assert result.coverage.covered == {NESTED_CHECKS: frozenset({2, 3, 4, 5, 6})}
    assert result.stopped.kind is StopKind.NO_FORK


def test_run_gathers_a_miss_from_every_fork_it_aimed_at(monkeypatch: pytest.MonkeyPatch) -> None:
    target = load_target("targets.flip.nested_checks::bucket")
    monkeypatch.setattr("pyct.run.run.solve", lambda *args: Unknown())

    result = run(target, {"x": 3})

    # an answer that gives no input is no input to run, and no reason to stop picking
    assert len(result.records) == 1
    assert result.misses == (
        Miss(site=Site(file=NESTED_CHECKS, line=3, col=11), why=MissWhy.UNKNOWN),
        Miss(site=Site(file=NESTED_CHECKS, line=2, col=7), why=MissWhy.UNKNOWN),
    )
    assert result.stopped.kind is StopKind.NO_FORK


@pytest.mark.usefixtures("deadline_fires_in_a_child")
def test_run_stops_on_the_budget_when_the_seed_forked_and_then_spent_it() -> None:
    target = load_target("targets.flip.spins_after_a_check::spin")

    result = run(target, {"x": 3}, limits=Limits(budget=Budget(seconds=0.05)))

    assert len(result.records) == 1
    assert result.records[0].failure == Failure(kind=FailureKind.TIMEOUT, detail="deadline passed")
    assert result.stopped.kind is StopKind.BUDGET


def test_run_stops_on_no_gain_when_the_last_inputs_covered_nothing_new() -> None:
    target = load_target("targets.flip.two_other_sides_empty::mark")

    result = run(target, {"x": 3, "y": 3}, limits=Limits(plateau=Plateau(inputs=1)))

    # the flip covers a subset of the seed's lines, and the other check's flip is never asked for
    assert len(result.records) == 2
    assert result.stopped == Stop(kind=StopKind.NO_GAIN, plateau=1)
    assert result.misses == ()


def test_run_prefers_no_fork_over_no_gain() -> None:
    target = load_target("targets.flip.other_side_empty::mark")

    result = run(target, {"x": 3}, limits=Limits(plateau=Plateau(inputs=1)))

    # both reasons hold after the flip; the emptied tree is the one the run names
    assert len(result.records) == 2
    assert result.stopped.kind is StopKind.NO_FORK


def test_run_does_not_count_a_solver_miss_toward_the_plateau() -> None:
    target = load_target("targets.flip.implied_check::narrow")
    events: list[str] = []

    result = run(
        target,
        {"x": 3},
        limits=Limits(plateau=Plateau(inputs=1)),
        tell=Tell(
            report=lambda *_: events.append("input"),
            missed=lambda *_: events.append("miss"),
        ),
    )

    # the miss sits inside the window and produced no input, so the window skips it
    assert events == ["input", "miss", "input"]
    assert result.stopped.kind is StopKind.NO_FORK


def test_run_records_a_miss_when_the_last_fork_cannot_be_flipped() -> None:
    target = load_target("targets.flip.implied_check::narrow")

    result = run(target, {"x": 3})

    assert result.misses == (
        Miss(site=Site(file=IMPLIED_CHECK, line=3, col=11), why=MissWhy.UNSAT),
    )
    # the inner fork gave no input, the outer one did, and then nothing was left
    assert len(result.records) == 2
    assert result.stopped.kind is StopKind.NO_FORK


@pytest.mark.parametrize(
    ("answer", "why"), [(Unknown(), MissWhy.UNKNOWN), (Timeout(), MissWhy.TIMEOUT)]
)
def test_run_records_what_the_solver_answered_when_it_gave_up(
    monkeypatch: pytest.MonkeyPatch, answer: Answer, why: MissWhy
) -> None:
    target = load_target("targets.flip.one_check::classify")
    monkeypatch.setattr("pyct.run.run.solve", lambda *args: answer)

    result = run(target, {"x": 3})

    assert result.misses == (Miss(site=Site(file=ONE_CHECK, line=2, col=7), why=why),)
    assert result.stopped.kind is StopKind.NO_FORK


def test_run_stops_as_a_failure_when_the_solver_died(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = load_target("targets.flip.one_check::classify")
    script = tmp_path / "cvc5"
    script.write_text(
        "#!/bin/sh\nPATH=/bin:/usr/bin\ncat > /dev/null\necho 'cvc5: boom' >&2\nexit 1\n"
    )
    script.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))

    result = run(target, {"x": 3})

    assert len(result.records) == 1
    assert result.stopped.kind is StopKind.SOLVER_FAILED
    assert result.stopped.detail == "cvc5: boom"
    assert result.misses == ()


def test_run_names_the_environment_it_ran_in() -> None:
    target = load_target("targets.flip.no_check::echo")

    result = run(target, {"x": 3})

    assert result.environment.python == platform.python_version()
    assert result.environment.platform == platform.platform()
    # the cvc5 on PATH answered the probe, so the summary can name which one solved the run
    assert result.environment.cvc5


def test_a_cvc5_that_will_not_say_its_version_does_not_stop_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = tmp_path / "cvc5"
    script.write_text("#!/bin/sh\nexit 1\n")
    script.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    target = load_target("targets.flip.no_check::echo")

    result = run(target, {"x": 3})

    assert result.environment.cvc5 is None
    assert result.stopped.kind is StopKind.NO_FORK

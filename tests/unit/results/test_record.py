import pytest

from pyct.core.branch import Branch, Site
from pyct.results.coverage import Coverage
from pyct.results.record import (
    Aim,
    Environment,
    InputRecord,
    Miss,
    MissWhy,
    RunResult,
    SolverCounts,
    Source,
    Stop,
    StopKind,
)
from tests.unit.environment import ENVIRONMENT

FORK = Branch(expression=["<", "x", 10], taken=True, site=Site(file="m.py", line=5, col=7))
COVERAGE = Coverage(covered={"m.py": frozenset()}, lines={"m.py": frozenset(range(1, 8))})


def test_run_result_holds_the_entry_its_records_and_coverage() -> None:
    record = InputRecord(args={"x": 1}, forks=(FORK,), covered_lines=frozenset({5, 6}))
    coverage = Coverage(covered={"m.py": frozenset({5, 6})}, lines={"m.py": frozenset(range(1, 8))})

    result = RunResult(
        entry="m::f",
        records=(record,),
        coverage=coverage,
        stopped=Stop(kind=StopKind.NO_FORK),
        environment=ENVIRONMENT,
    )

    assert result.records[0].args == {"x": 1}
    assert result.records[0].covered_lines == frozenset({5, 6})
    assert result.coverage.total == {"m.py": 7}


def test_an_input_record_holds_the_forks_the_input_took() -> None:
    record = InputRecord(args={"x": 1}, forks=(FORK,), covered_lines=frozenset({5, 6}))

    assert record.forks == (FORK,)


def test_an_input_record_ends_well_and_loses_nothing_by_default() -> None:
    record = InputRecord(args={"x": 1}, forks=(), covered_lines=frozenset())

    assert record.failure is None
    assert record.downgrades == ()


def test_an_input_comes_from_the_seed_or_from_the_solver() -> None:
    assert Source.SEED.value == "seed"
    assert Source.SOLVER.value == "solver"


def test_an_aim_names_the_fork_it_went_for_and_where_on_the_path() -> None:
    aim = Aim(site=Site(file="m.py", line=5, col=7), position=0)

    assert aim.site == Site(file="m.py", line=5, col=7)
    assert aim.position == 0


def test_an_input_record_is_a_seed_with_no_aim_by_default() -> None:
    record = InputRecord(args={"x": 1}, forks=(), covered_lines=frozenset())

    assert record.source is Source.SEED
    assert record.aim is None
    assert record.mismatch_at is None


def test_a_stop_kind_is_the_words_on_the_stderr_line() -> None:
    assert StopKind.NO_FORK.value == "no fork to flip"
    assert StopKind.BUDGET.value == "budget spent"
    assert StopKind.NO_GAIN.value == "no gain"
    assert StopKind.SOLVER_FAILED.value == "solver failed"


def test_a_stop_carries_no_detail_unless_given_one() -> None:
    assert Stop(kind=StopKind.NO_FORK).detail is None
    assert Stop(kind=StopKind.SOLVER_FAILED, detail="cvc5: boom").detail == "cvc5: boom"


def test_a_no_gain_stop_reads_its_plateau_into_the_reason() -> None:
    assert Stop(kind=StopKind.NO_GAIN, plateau=3).reason == "no gain in 3 inputs"


def test_every_other_stop_reads_as_its_bare_kind() -> None:
    assert Stop(kind=StopKind.NO_FORK).reason == "no fork to flip"


def test_a_no_gain_stop_without_a_plateau_is_refused() -> None:
    # the reason names the N, so a stop that has none could not be written down
    with pytest.raises(ValueError, match="names its plateau"):
        Stop(kind=StopKind.NO_GAIN)


def test_a_miss_names_the_fork_and_what_the_solver_answered() -> None:
    miss = Miss(site=Site(file="m.py", line=5, col=7), why=MissWhy.UNSAT)

    assert miss.site == Site(file="m.py", line=5, col=7)
    assert miss.why.value == "unsat"
    assert MissWhy.UNKNOWN.value == "unknown"
    assert MissWhy.TIMEOUT.value == "timeout"


def test_a_run_result_says_why_it_stopped_and_misses_nothing_by_default() -> None:
    record = InputRecord(args={"x": 1}, forks=(), covered_lines=frozenset())
    coverage = Coverage(covered={"m.py": frozenset()}, lines={"m.py": frozenset(range(1, 8))})

    result = RunResult(
        entry="m::f",
        records=(record,),
        coverage=coverage,
        stopped=Stop(kind=StopKind.NO_FORK),
        environment=ENVIRONMENT,
    )

    assert result.stopped.kind is StopKind.NO_FORK
    assert result.misses == ()


def result_of(*records: InputRecord, misses: tuple[Miss, ...] = ()) -> RunResult:
    """A run result whose only facts that matter here are its records and its misses."""
    return RunResult(
        entry="m::f",
        records=records,
        coverage=COVERAGE,
        stopped=Stop(kind=StopKind.NO_FORK),
        environment=ENVIRONMENT,
        misses=misses,
    )


def input_from(source: Source) -> InputRecord:
    return InputRecord(args={"x": 1}, forks=(), covered_lines=frozenset(), source=source)


def miss(why: MissWhy) -> Miss:
    return Miss(site=Site(file="m.py", line=5, col=7), why=why)


def test_an_environment_names_the_interpreter_the_solver_and_the_machine() -> None:
    environment = Environment(python="3.12.0", cvc5="1.2.1", platform="Test-1.0-arm64")

    assert environment.python == "3.12.0"
    assert environment.cvc5 == "1.2.1"
    assert environment.platform == "Test-1.0-arm64"


def test_an_environment_names_no_cvc5_when_the_probe_failed() -> None:
    assert Environment(python="3.12.0", cvc5=None, platform="Test-1.0-arm64").cvc5 is None


def test_a_run_result_carries_the_environment_it_ran_in() -> None:
    assert result_of(input_from(Source.SEED)).environment == ENVIRONMENT


def test_a_run_result_counts_one_input_per_record() -> None:
    assert result_of(input_from(Source.SEED), input_from(Source.SOLVER)).inputs == 2


def test_the_sat_count_is_the_inputs_the_solver_gave() -> None:
    result = result_of(input_from(Source.SEED), input_from(Source.SOLVER))

    # the seed is nobody's answer, so only the solver's inputs count as sat
    assert result.solver.sat == 1


def test_the_other_counts_are_the_misses_by_what_the_solver_said() -> None:
    result = result_of(
        input_from(Source.SEED),
        misses=(miss(MissWhy.UNSAT), miss(MissWhy.TIMEOUT), miss(MissWhy.UNSAT)),
    )

    assert result.solver == SolverCounts(sat=0, unsat=2, unknown=0, timeout=1)


def test_a_run_that_asked_the_solver_nothing_counts_no_answers() -> None:
    assert result_of(input_from(Source.SEED)).solver == SolverCounts(
        sat=0, unsat=0, unknown=0, timeout=0
    )

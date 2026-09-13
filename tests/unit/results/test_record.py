from pyct.core.branch import Branch, Site
from pyct.results.coverage import Coverage
from pyct.results.record import Aim, InputRecord, Miss, MissWhy, RunResult, Source, Stop, StopKind

FORK = Branch(expression=["<", "x", 10], taken=True, site=Site(file="m.py", line=5, col=7))


def test_run_result_holds_the_entry_its_records_and_coverage() -> None:
    record = InputRecord(args={"x": 1}, forks=(FORK,), covered_lines=frozenset({5, 6}))
    coverage = Coverage(covered={"m.py": frozenset({5, 6})}, total={"m.py": 7})

    result = RunResult(
        entry="m::f", records=(record,), coverage=coverage, stopped=Stop(kind=StopKind.NO_FORK)
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


def test_an_input_that_matched_the_plan_reached_it() -> None:
    record = InputRecord(args={"x": 1}, forks=(), covered_lines=frozenset())

    assert record.reached is True


def test_an_input_that_left_the_plan_did_not_reach_it() -> None:
    record = InputRecord(
        args={"x": 1},
        forks=(FORK,),
        covered_lines=frozenset({5}),
        source=Source.SOLVER,
        aim=Aim(site=Site(file="m.py", line=5, col=7), position=0),
        mismatch_at=0,
    )

    assert record.reached is False


def test_a_stop_kind_is_the_words_on_the_stderr_line() -> None:
    assert StopKind.NO_FORK.value == "no fork to flip"
    assert StopKind.BUDGET.value == "budget spent"
    assert StopKind.ONE_ATTEMPT.value == "after one attempt"
    assert StopKind.SOLVER_FAILED.value == "solver failed"


def test_a_stop_carries_no_detail_unless_given_one() -> None:
    assert Stop(kind=StopKind.NO_FORK).detail is None
    assert Stop(kind=StopKind.SOLVER_FAILED, detail="cvc5: boom").detail == "cvc5: boom"


def test_a_miss_names_the_fork_and_what_the_solver_answered() -> None:
    miss = Miss(site=Site(file="m.py", line=5, col=7), why=MissWhy.UNSAT)

    assert miss.site == Site(file="m.py", line=5, col=7)
    assert miss.why.value == "unsat"
    assert MissWhy.UNKNOWN.value == "unknown"
    assert MissWhy.TIMEOUT.value == "timeout"


def test_a_run_result_says_why_it_stopped_and_misses_nothing_by_default() -> None:
    record = InputRecord(args={"x": 1}, forks=(), covered_lines=frozenset())
    coverage = Coverage(covered={"m.py": frozenset()}, total={"m.py": 7})

    result = RunResult(
        entry="m::f", records=(record,), coverage=coverage, stopped=Stop(kind=StopKind.NO_FORK)
    )

    assert result.stopped.kind is StopKind.NO_FORK
    assert result.misses == ()

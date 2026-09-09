from pyct.core.branch import Branch, Site
from pyct.results.coverage import Coverage
from pyct.results.failure import Failure, FailureKind
from pyct.results.record import InputRecord, RunResult

FORK = Branch(expression=["<", "x", 10], taken=True, site=Site(file="m.py", line=5, col=7))


def test_run_result_holds_the_entry_its_records_and_coverage() -> None:
    record = InputRecord(args={"x": 1}, forks=(FORK,), covered_lines=frozenset({5, 6}))
    coverage = Coverage(covered={"m.py": frozenset({5, 6})}, total={"m.py": 7})

    result = RunResult(entry="m::f", records=(record,), coverage=coverage)

    assert result.records[0].args == {"x": 1}
    assert result.records[0].covered_lines == frozenset({5, 6})
    assert result.coverage.total == {"m.py": 7}


def test_an_input_record_holds_the_forks_the_input_took() -> None:
    record = InputRecord(args={"x": 1}, forks=(FORK,), covered_lines=frozenset({5, 6}))

    assert record.forks == (FORK,)


def test_an_input_record_holds_how_it_ended_and_what_was_lost() -> None:
    failure = Failure(kind=FailureKind.TARGET_RAISED, detail="ValueError: too small")

    record = InputRecord(
        args={"x": 1},
        forks=(),
        covered_lines=frozenset(),
        failure=failure,
        downgrades=("__abs__",),
    )

    assert record.failure == failure
    assert record.downgrades == ("__abs__",)


def test_an_input_record_ends_well_and_loses_nothing_by_default() -> None:
    record = InputRecord(args={"x": 1}, forks=(), covered_lines=frozenset())

    assert record.failure is None
    assert record.downgrades == ()

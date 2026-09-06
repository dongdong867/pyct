from pyct.results.coverage import Coverage
from pyct.results.record import InputRecord, RunResult


def test_run_result_holds_the_entry_its_records_and_coverage() -> None:
    record = InputRecord(args={"x": 1}, new_lines=frozenset({5, 6}))
    coverage = Coverage(covered={"m.py": frozenset({5, 6})}, total={"m.py": 7})

    result = RunResult(entry="m::f", records=(record,), coverage=coverage)

    assert result.records[0].args == {"x": 1}
    assert result.coverage.total == {"m.py": 7}

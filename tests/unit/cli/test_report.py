import pytest

from pyct.cli import _report
from pyct.results.coverage import Coverage
from pyct.results.record import InputRecord

COVERAGE = Coverage(covered={"m.py": frozenset({5})}, total={"m.py": 7})
RECORD = InputRecord(args={"x": 1}, forks=(), covered_lines=frozenset({5}))


def test_report_writes_the_readable_trace_to_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    _report(RECORD, COVERAGE)

    captured = capsys.readouterr()
    assert captured.err.splitlines() == [
        'seed {"x": 1}',
        "covered 1 of 7 lines in m.py",
        "ended returned",
        "downgrades none",
    ]


def test_report_leaves_stdout_one_json_line(capsys: pytest.CaptureFixture[str]) -> None:
    _report(RECORD, COVERAGE)

    assert len(capsys.readouterr().out.splitlines()) == 1

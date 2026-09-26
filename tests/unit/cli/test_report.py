import io
import sys

import pytest

from pyct.cli import _report
from pyct.results.coverage import Coverage
from pyct.results.jsonl import render
from pyct.results.record import InputRecord

COVERAGE = Coverage(covered={"m.py": frozenset({5})}, lines={"m.py": frozenset(range(1, 8))})
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


def test_report_flushes_the_line_when_stdout_is_a_pipe(monkeypatch: pytest.MonkeyPatch) -> None:
    # a pipe is block-buffered: without a flush the line waits in memory until exit
    pipe = io.TextIOWrapper(io.BytesIO(), encoding="utf-8", write_through=False)
    monkeypatch.setattr(sys, "stdout", pipe)

    _report(RECORD, COVERAGE)

    assert pipe.buffer.getvalue().decode() == render(RECORD, COVERAGE) + "\n"


class Writes(io.StringIO):
    """A stdout that keeps each write call apart."""

    def __init__(self) -> None:
        super().__init__()
        self.writes: list[str] = []

    def write(self, text: str, /) -> int:
        if text:
            self.writes.append(text)
        return super().write(text)


def test_report_writes_the_line_and_its_end_at_once(monkeypatch: pytest.MonkeyPatch) -> None:
    # a Ctrl-C between two writes would leave a line with no end for the next one to join
    stdout = Writes()
    monkeypatch.setattr(sys, "stdout", stdout)

    _report(RECORD, COVERAGE)

    assert stdout.writes == [render(RECORD, COVERAGE) + "\n"]

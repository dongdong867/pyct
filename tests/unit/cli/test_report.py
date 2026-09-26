import io
import sys
from collections.abc import Sequence

import pytest

from pyct.cli import _report
from pyct.core.branch import Branch, Expression, Site
from pyct.results.coverage import Coverage
from pyct.results.jsonl import render
from pyct.results.printed import printed_forks
from pyct.results.record import InputRecord
from pyct.results.trace import render_trace

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


def _count_cuts(monkeypatch: pytest.MonkeyPatch, calls: list[str], module: str) -> None:
    """Note each time ``module`` cuts a record's forks, by the module's name."""

    def counted(forks: Sequence[Branch]) -> tuple[Expression, ...]:
        calls.append(module)
        return printed_forks(forks)

    monkeypatch.setattr(f"{module}.printed_forks", counted)


def test_report_cuts_the_forks_once_for_both_lines(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # a loop's forks each hold the string of every pass before theirs, past the cap from the
    # eighth pass on
    term: Expression = "s"
    forks: list[Branch] = []
    for i in range(40):
        forks.append(
            Branch(expression=[">", ["len", term], i], taken=True, site=Site("m.py", 5, 7))
        )
        term = ["+", ["[:]", term, None, 1], ["[:]", term, 2, None]]
    record = InputRecord(args={"s": "abc"}, forks=tuple(forks), covered_lines=frozenset({5}))
    calls: list[str] = []
    for module in ("pyct.cli", "pyct.results.jsonl", "pyct.results.trace"):
        _count_cuts(monkeypatch, calls, module)

    _report(record, COVERAGE)

    # the report cuts the forks once and hands the cut to both lines, which cut none of their own
    assert calls == ["pyct.cli"]
    # and each line is what it would be alone
    captured = capsys.readouterr()
    assert captured.out == render(record, COVERAGE) + "\n"
    assert captured.err == render_trace(record, COVERAGE)
    assert " nodes)" in captured.err

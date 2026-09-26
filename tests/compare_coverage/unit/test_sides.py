"""How either side's process becomes a report: its line, and every way it fails."""

import json

import pytest

from tools.compare_coverage.process import Finished
from tools.compare_coverage.sides import (
    SideReport,
    last_line,
    lines_of,
    optional_count,
    optional_text,
    read_report,
)


def parse(line: dict[str, object]) -> SideReport:
    return SideReport(file=str(line["file"]), covered=lines_of(line["covered"]))


LINE = json.dumps({"file": "/t.py", "covered": [2, 3]})


def test_the_last_line_with_the_key_is_the_report_whatever_the_target_printed() -> None:
    stdout = f"target says hi\n{json.dumps({'other': 1})}\n{LINE}\n[1, 2]\n"

    report = read_report(Finished(0, stdout, ""), "covered", parse)

    assert report == SideReport(file="/t.py", covered=frozenset({2, 3}))


def test_no_line_with_the_key_is_no_summary_line() -> None:
    report = read_report(Finished(0, "hello\n", ""), "covered", parse)

    assert report == SideReport(failure="no summary line")


def test_a_non_zero_exit_names_the_code_and_the_last_stderr_line_and_keeps_the_lines() -> None:
    finished = Finished(1, f"{LINE}\n", "first\nlast words\n\n")

    report = read_report(finished, "covered", parse)

    assert report.failure == "exit 1: last words"
    assert report.covered == frozenset({2, 3})


def test_a_non_zero_exit_without_a_line_names_the_exit() -> None:
    report = read_report(Finished(2, "", ""), "covered", parse)

    assert report == SideReport(failure="exit 2: nothing on stderr")


def test_a_stopped_side_names_how_long_it_ran() -> None:
    report = read_report(Finished(None, "", "", stopped_after=61.5), "covered", parse)

    assert report == SideReport(failure="stopped after 61.5 s")


def test_a_line_that_is_not_a_report_fails_the_side_naming_why() -> None:
    stdout = json.dumps({"file": "/t.py", "covered": "all"}) + "\n"

    report = read_report(Finished(0, stdout, ""), "covered", parse)

    assert report.failure is not None
    assert report.failure.startswith("unreadable summary line: ValueError(")


def test_last_line_skips_blank_lines() -> None:
    assert last_line("a\n  b  \n\n") == "b"
    assert last_line("") == "nothing on stderr"


@pytest.mark.parametrize("value", ["2", [2, "3"], [True], None])
def test_lines_must_be_a_list_of_line_numbers(value: object) -> None:
    with pytest.raises(ValueError, match="list of line numbers"):
        lines_of(value)


def test_optional_fields_take_their_type_or_none() -> None:
    assert optional_text(None) is None
    assert optional_text("x") == "x"
    assert optional_count(None) is None
    assert optional_count(3) == 3
    with pytest.raises(ValueError, match="text"):
        optional_text(3)
    with pytest.raises(ValueError, match="count"):
        optional_count(True)

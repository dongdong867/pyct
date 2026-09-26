"""What the checker prints: a JSON line per row, the summary line, and the table on stderr."""

import json
from dataclasses import replace

from tools.compare_coverage.output import (
    Facts,
    counts,
    row_line,
    summary_line,
    table_line,
    totals_line,
)
from tools.compare_coverage.rows import Row, SideView, Status

V2 = SideView(file="/t.py", covered=(2, 3), stopped="no fork to flip", inputs=2, failure=None)
LEGACY = SideView(file="/t.py", covered=(2, 3, 5), stopped="exhausted", inputs=4, failure=None)
DIFFERS = Row(
    set="v2",
    status=Status.DIFFERS,
    file="/t.py",
    target="m::f",
    seed={"x": 0},
    own_lines=(2, 3, 5),
    only_legacy=(5,),
    v2=V2,
    legacy=LEGACY,
)
NOT_LISTED = Row(set="fixtures", status=Status.NOT_LISTED, file="/u.py")


def test_a_row_line_holds_every_field_of_the_row() -> None:
    assert json.loads(row_line(DIFFERS)) == {
        "set": "v2",
        "target": "m::f",
        "seed": {"x": 0},
        "file": "/t.py",
        "own_lines": [2, 3, 5],
        "status": "differs",
        "only_legacy": [5],
        "only_v2": [],
        "v2": {
            "file": "/t.py",
            "covered": [2, 3],
            "stopped": "no fork to flip",
            "inputs": 2,
            "failure": None,
        },
        "legacy": {
            "file": "/t.py",
            "covered": [2, 3, 5],
            "stopped": "exhausted",
            "inputs": 4,
            "failure": None,
        },
        "record": None,
        "change": None,
        "left_out": None,
    }


def test_a_row_with_no_sides_has_null_sides() -> None:
    line = json.loads(row_line(NOT_LISTED))

    assert (line["status"], line["v2"], line["legacy"], line["target"]) == (
        "not listed",
        None,
        None,
        None,
    )


def test_counts_name_every_status_and_every_mark() -> None:
    accepted = replace(DIFFERS, record="accepted")

    assert counts([DIFFERS, accepted, NOT_LISTED]) == {
        "same": 0,
        "differs": 2,
        "v2 failed": 0,
        "legacy failed": 0,
        "both failed": 0,
        "not listed": 1,
        "left out": 0,
        "accepted": 1,
        "changed": 0,
    }


def test_the_summary_line_has_counts_limits_commits_and_environment_and_no_target() -> None:
    facts = Facts(
        commits={"v2": "abc", "legacy": None},
        python={"v2": "3.12.1", "legacy": "3.12.2"},
        cvc5="cvc5 1.3.4",
        platform="Test-1.0",
    )
    limits = {"v2": {"budget": 5.0}, "legacy": {"budget": 5.0}}

    line = json.loads(summary_line([DIFFERS], limits, facts))

    assert "target" not in line
    assert line["statuses"]["differs"] == 1
    assert line["limits"] == limits
    assert line["commits"] == {"v2": "abc", "legacy": None}
    assert line["environment"] == {
        "python": {"v2": "3.12.1", "legacy": "3.12.2"},
        "cvc5": "cvc5 1.3.4",
        "platform": "Test-1.0",
    }


def test_a_table_line_names_both_sides_the_status_and_the_lines_one_side_covered() -> None:
    assert table_line(DIFFERS) == (
        "v2  m::f  v2 covered 2 of 3 (no fork to flip, 2 inputs)"
        "  legacy covered 3 of 3 (exhausted, 4 inputs)  differs  only legacy: 5"
    )


def test_a_table_line_names_a_mark_a_change_and_each_failure() -> None:
    failed = SideView(file=None, covered=(), stopped=None, inputs=None, failure="exit 2: no")
    row = replace(
        DIFFERS,
        status=Status.V2_FAILED,
        only_legacy=(),
        v2=failed,
        record="changed",
        change="status was differs, now v2 failed",
    )

    assert table_line(row) == (
        "v2  m::f  v2 covered 0 of 3 (no stop, ? inputs)"
        "  legacy covered 3 of 3 (exhausted, 4 inputs)  v2 failed, changed"
        "  changed: status was differs, now v2 failed; v2: exit 2: no"
    )


def test_a_table_line_for_a_file_names_the_file_and_the_reason() -> None:
    left = Row(set="v2", status=Status.LEFT_OUT, file="/b.py", left_out="fails to import")
    only_v2 = replace(DIFFERS, only_legacy=(), only_v2=(7, 8))

    assert table_line(NOT_LISTED) == "fixtures  /u.py  not listed"
    assert table_line(left) == "v2  /b.py  left out  fails to import"
    assert table_line(only_v2).endswith("differs  only v2: 7, 8")


def test_the_totals_line_gives_every_count() -> None:
    assert totals_line([NOT_LISTED]) == (
        "totals: same 0, differs 0, v2 failed 0, legacy failed 0, both failed 0, "
        "not listed 1, left out 0, accepted 0, changed 0"
    )

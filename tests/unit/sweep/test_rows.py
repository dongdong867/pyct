import json
import platform

from pyct.sweep.rows import LIMITS, Row, Status, closing, row_line, summary_line, told

LISTED = Row("p.m", "f", Status.LISTED, seed={"n": 0})
SKIPPED = Row("p.m", "g", Status.SKIPPED, reason="no parameter to vary")
FAILED = Row("p.gone", None, Status.FAILED, reason="cannot import p.gone: ValueError('boom')")


def test_a_row_has_the_same_six_keys_null_when_empty() -> None:
    assert json.loads(row_line(SKIPPED)) == {
        "module": "p.m",
        "name": "g",
        "status": "skipped",
        "seed": None,
        "reason": "no parameter to vary",
        "run": None,
    }


def test_the_summary_counts_each_status_and_says_what_was_listed() -> None:
    summary = json.loads(summary_line("p", [LISTED, SKIPPED, FAILED]))

    assert summary == {
        "swept": "p",
        "stopped": "listed",
        "ran": 0,
        "failed": 1,
        "skipped": 1,
        "listed": 1,
        "covered": {},
        "total": {},
        "limits": dict(LIMITS),
        "environment": {
            "python": platform.python_version(),
            "cvc5": None,
            "platform": platform.platform(),
        },
    }


def test_each_row_but_a_listed_one_is_told_on_stderr() -> None:
    assert told(LISTED) is None
    assert told(SKIPPED) == "skipped p.m::g: no parameter to vary"
    assert told(FAILED) == "failed p.gone: cannot import p.gone: ValueError('boom')"


def test_the_closing_lines_count_the_rows() -> None:
    assert closing("p", [LISTED, SKIPPED, FAILED]) == (
        "listed 3 entries: 1 listed, 1 skipped, 1 failed\nstopped: listed\n"
    )


def test_the_closing_lines_say_when_nothing_was_found() -> None:
    assert closing("p", [FAILED]) == (
        "found no entries in p\nlisted 1 entries: 0 listed, 0 skipped, 1 failed\nstopped: listed\n"
    )


def test_rows_order_by_module_then_name_with_a_modules_own_row_first() -> None:
    rows = [LISTED, Row("p.m", None, Status.FAILED, reason="x"), SKIPPED]
    assert [row.name for row in sorted(rows, key=lambda row: row.order)] == [None, "f", "g"]

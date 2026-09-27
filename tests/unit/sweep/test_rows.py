import json

from pyct.sweep.rows import Row, Status, count, row_line, running, told

LISTED = Row("p.m", "f", Status.LISTED, seed={"n": 0})
SKIPPED = Row("p.m", "g", Status.SKIPPED, reason="no parameter to vary")
FAILED = Row("p.gone", None, Status.FAILED, reason="cannot import p.gone: ValueError('boom')")
RUN = {
    "stopped": "no fork to flip",
    "covered": {"a.py": [1, 2], "b.py": [3]},
    "total": {"a.py": 4, "b.py": 5},
}
RAN = Row("p.m", "f", Status.RAN, seed={"n": 0}, run=RUN)


def test_a_row_has_the_same_six_keys_null_when_empty() -> None:
    assert json.loads(row_line(SKIPPED)) == {
        "module": "p.m",
        "name": "g",
        "status": "skipped",
        "seed": None,
        "reason": "no parameter to vary",
        "run": None,
    }


def test_a_row_that_ran_carries_its_summary_line_unchanged() -> None:
    assert json.loads(row_line(RAN))["run"] == RUN


def test_each_row_but_a_listed_one_is_told_on_stderr() -> None:
    assert told(LISTED) is None
    assert told(SKIPPED) == "skipped p.m::g: no parameter to vary"
    assert told(FAILED) == "failed p.gone: cannot import p.gone: ValueError('boom')"


def test_a_row_that_ran_is_told_with_its_lines_over_every_file_and_why_it_stopped() -> None:
    assert told(RAN) == "ran p.m::f: covered 3 of 9 lines, stopped: no fork to flip"


def test_a_failed_entry_is_told_by_its_name() -> None:
    failed = Row("p.m", "f", Status.FAILED, seed={"n": 0}, reason="killed by SIGSEGV")

    assert told(failed) == "failed p.m::f: killed by SIGSEGV"


def test_the_line_before_a_run_names_the_entry_its_seed_and_how_far_the_sweep_is() -> None:
    assert running(LISTED, 2, 3) == 'running p.m::f {"n": 0} (2 of 3)'


def test_rows_are_counted_by_status() -> None:
    assert count([LISTED, SKIPPED, RAN, SKIPPED], Status.SKIPPED) == 2


def test_rows_order_by_module_then_name_with_a_modules_own_row_first() -> None:
    rows = [LISTED, Row("p.m", None, Status.FAILED, reason="x"), SKIPPED]
    assert [row.name for row in sorted(rows, key=lambda row: row.order)] == [None, "f", "g"]

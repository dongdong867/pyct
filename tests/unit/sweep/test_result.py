import json
import platform

from pyct.sweep.result import SweepLimits, SweepResult, SweepStop, closing, summary_line
from pyct.sweep.rows import Row, Status

LISTED = Row("p.m", "f", Status.LISTED, seed={"n": 0})
SKIPPED = Row("p.m", "g", Status.SKIPPED, reason="no parameter to vary")
FAILED = Row("p.gone", None, Status.FAILED, reason="cannot import p.gone: ValueError('boom')")
RAN = Row("p.m", "f", Status.RAN, seed={"n": 0}, run={})


def test_the_grace_is_a_minute() -> None:
    # the limit on one module's import while listing, and on a run past its budget
    assert SweepLimits().grace == 60.0


def test_the_summary_counts_each_status_and_says_what_was_listed() -> None:
    result = SweepResult("p", (LISTED, SKIPPED, FAILED), SweepStop.LISTED, SweepLimits())

    assert json.loads(summary_line(result)) == {
        "swept": "p",
        "stopped": "listed",
        "ran": 0,
        "failed": 1,
        "skipped": 1,
        "listed": 1,
        "covered": {},
        "total": {},
        "limits": {"budget": 30.0, "plateau": 5, "solver_timeout": 10.0, "total_budget": None},
        "environment": {
            "python": platform.python_version(),
            "cvc5": None,
            "platform": platform.platform(),
        },
    }


def test_the_summary_of_a_run_sorts_its_files_and_lines_and_names_its_limits_and_cvc5() -> None:
    limits = SweepLimits(budget=20.0, plateau=3, solver_timeout=1.0, total_budget=9.0, grace=5.0)
    covered = {"b.py": frozenset({3, 1}), "a.py": frozenset({2})}
    result = SweepResult(
        "p", (RAN,), SweepStop.DONE, limits, covered, {"b.py": 4, "a.py": 2}, "1.3.4"
    )
    summary = json.loads(summary_line(result))

    assert summary["stopped"] == "done"
    assert list(summary["covered"].items()) == [("a.py", [2]), ("b.py", [1, 3])]
    assert list(summary["total"].items()) == [("a.py", 2), ("b.py", 4)]
    expected = {"budget": 20.0, "plateau": 3, "solver_timeout": 1.0, "total_budget": 9.0}
    assert summary["limits"] == expected
    assert summary["environment"]["cvc5"] == "1.3.4"


def test_the_closing_lines_of_a_listing_count_the_rows() -> None:
    result = SweepResult("p", (LISTED, SKIPPED, FAILED), SweepStop.LISTED, SweepLimits())

    assert closing(result) == ("listed 3 entries: 1 listed, 1 skipped, 1 failed\nstopped: listed\n")


def test_the_closing_lines_say_when_nothing_was_found() -> None:
    result = SweepResult("p", (FAILED,), SweepStop.LISTED, SweepLimits())

    assert closing(result) == (
        "found no entries in p\nlisted 1 entries: 0 listed, 0 skipped, 1 failed\nstopped: listed\n"
    )


def test_the_closing_lines_of_a_run_count_the_rows_and_the_lines_over_one_file() -> None:
    result = SweepResult(
        "p", (RAN, SKIPPED), SweepStop.DONE, SweepLimits(), {"a.py": frozenset({1, 2})}, {"a.py": 5}
    )

    assert closing(result) == (
        "swept 2 entries: 1 ran, 1 skipped, 0 failed\n"
        "covered 2 of 5 lines in 1 file\n"
        "stopped: done\n"
    )


def test_the_closing_lines_of_a_run_count_every_file() -> None:
    covered = {"a.py": frozenset({1}), "b.py": frozenset({2, 3})}
    result = SweepResult(
        "p", (RAN,), SweepStop.TOTAL_BUDGET_SPENT, SweepLimits(), covered, {"a.py": 2, "b.py": 4}
    )

    assert closing(result).splitlines()[1:] == [
        "covered 3 of 6 lines in 2 files",
        "stopped: total budget spent",
    ]


def test_the_closing_lines_of_a_run_that_found_nothing_say_so() -> None:
    result = SweepResult("p", (), SweepStop.DONE, SweepLimits())

    assert closing(result).splitlines() == [
        "found no entries in p",
        "swept 0 entries: 0 ran, 0 skipped, 0 failed",
        "covered 0 of 0 lines in 0 files",
        "stopped: done",
    ]

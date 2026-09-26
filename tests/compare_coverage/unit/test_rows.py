"""A row from an entry, its body and the two reports: status first from failures, then lines."""

from pathlib import Path

from tools.compare_coverage.body import Body
from tools.compare_coverage.entries import Entry, Unlisted
from tools.compare_coverage.rows import (
    Reports,
    SideView,
    Status,
    compared_row,
    left_out_row,
    unlisted_row,
    unreadable_row,
)
from tools.compare_coverage.sides import SideReport

FILE = Path("/checkout/targets/t.py")
ENTRY = Entry(set="v2", module="targets.t", name="f", seed={"x": 0})
# own lines 2, 3 and 5; line 4 is inside the statement on line 3
BODY = Body(own_lines=frozenset({2, 3, 5}), first_line={2: 2, 3: 3, 4: 3, 5: 5})


def report(*lines: int, failure: str | None = None, file: Path = FILE) -> SideReport:
    return SideReport(
        file=str(file), covered=frozenset(lines), stopped="done", inputs=2, failure=failure
    )


def test_both_sides_on_the_same_own_lines_are_same() -> None:
    # line 4 stands for 3, and line 1 is outside the body
    row = compared_row(ENTRY, FILE, BODY, Reports(v2=report(1, 2, 4), legacy=report(2, 3)))

    assert row.status is Status.SAME
    assert row.own_lines == (2, 3, 5)
    assert row.v2 == SideView(
        file=str(FILE), covered=(2, 3), stopped="done", inputs=2, failure=None
    )
    assert (row.only_legacy, row.only_v2) == ((), ())
    assert (row.target, row.seed, row.file) == ("targets.t::f", {"x": 0}, str(FILE))


def test_lines_only_one_side_covered_make_a_difference() -> None:
    row = compared_row(ENTRY, FILE, BODY, Reports(v2=report(2, 5), legacy=report(2, 3)))

    assert row.status is Status.DIFFERS
    assert row.only_legacy == (3,)
    assert row.only_v2 == (5,)


def test_a_failed_side_is_shown_but_not_compared() -> None:
    reports = Reports(v2=report(2, failure="exit 1: boom"), legacy=report(2, 3))

    row = compared_row(ENTRY, FILE, BODY, reports)

    assert row.status is Status.V2_FAILED
    assert row.v2 is not None
    assert row.v2.covered == (2,)
    assert (row.only_legacy, row.only_v2) == ((), ())


def test_each_side_can_fail_alone_or_both_together() -> None:
    failed = report(failure="no summary line")

    legacy = compared_row(ENTRY, FILE, BODY, Reports(v2=report(2), legacy=failed))
    both = compared_row(ENTRY, FILE, BODY, Reports(v2=failed, legacy=failed))

    assert legacy.status is Status.LEGACY_FAILED
    assert both.status is Status.BOTH_FAILED


def test_a_side_that_loaded_another_file_fails_naming_both_and_shows_no_lines() -> None:
    elsewhere = Path("/usr/lib/python/t.py")

    row = compared_row(
        ENTRY, FILE, BODY, Reports(v2=report(2, 3, file=elsewhere), legacy=report(2, 3))
    )

    assert row.status is Status.V2_FAILED
    assert row.v2 is not None
    assert row.v2.failure == f"loaded {elsewhere}, the entry names {FILE}"
    assert row.v2.covered == ()


def test_a_side_with_its_own_failure_keeps_that_failure(tmp_path: Path) -> None:
    reports = Reports(v2=SideReport(failure="exit 2: refused"), legacy=report(2))

    row = compared_row(ENTRY, FILE, BODY, reports)

    assert row.v2 == SideView(
        file=None, covered=(), stopped=None, inputs=None, failure="exit 2: refused"
    )


def test_a_report_that_names_no_file_fails_its_side() -> None:
    nameless = SideReport(stopped="done", inputs=1)

    row = compared_row(ENTRY, FILE, BODY, Reports(v2=nameless, legacy=nameless))

    assert row.status is Status.BOTH_FAILED
    assert row.v2 is not None
    assert row.v2.failure == "the report names no file"


def test_an_unreadable_body_fails_both_sides_with_the_reason() -> None:
    row = unreadable_row(ENTRY, FILE, "no def")

    assert row.status is Status.BOTH_FAILED
    assert row.v2 == row.legacy == SideView(None, (), None, None, "no def")


def test_a_left_out_entry_and_an_unlisted_file_have_rows_of_their_own() -> None:
    left = Entry(set="v2", module="targets.t", left_out="why")

    assert left_out_row(left, FILE).status is Status.LEFT_OUT
    assert left_out_row(left, FILE).left_out == "why"
    unlisted = unlisted_row(Unlisted(set="fixtures", file=FILE))
    assert (unlisted.status, unlisted.set, unlisted.file) == (
        Status.NOT_LISTED,
        "fixtures",
        str(FILE),
    )

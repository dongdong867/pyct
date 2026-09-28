"""A record's range: the lines a row where a side ran its whole budget showed in some runs.

keep-a-budget-bound-compare-row-stable: a record may hold ``varies``, and ``--accept`` keeps a
matched record, widens an unmatched one when a side ran its whole budget, and otherwise
replaces it as before.
"""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from tools.compare_coverage.accepted import (
    Accepted,
    Record,
    RecordsError,
    Varies,
    mark,
    passes,
    read_records,
    rewritten,
    write_records,
)
from tools.compare_coverage.entries import Origin
from tools.compare_coverage.rows import Row, SideView, Status
from tools.compare_coverage.sides import Limits

LIMITS = Limits(budget=5.0, plateau=5, solver_timeout=10.0)
BUDGET = LIMITS.budget
ROOTS = {Origin.V2: Path("/work/v2"), Origin.LEGACY: Path("/work/legacy")}
HEADER = json.dumps({"budget": 5.0, "plateau": 5, "solver_timeout": 10.0})

# a side that ran for less than the budget, and one that ran all of it
QUICK = SideView(file="/t.py", covered=(2, 3), stopped="exhausted", inputs=2, failure=None)
SPENT = replace(QUICK, seconds=5.3)
QUICK = replace(QUICK, seconds=1.2)

ROW = Row(
    set="v2",
    status=Status.DIFFERS,
    file="/t.py",
    target="m::f",
    seed={"s": "a"},
    only_v2=(5,),
    v2=QUICK,
    legacy=QUICK,
)
EXACT = Record(
    set="v2", target="m::f", seed={"s": "a"}, status="differs", only_legacy=(), only_v2=(5,)
)
RANGE = replace(EXACT, varies=Varies(only_v2=(4, 6)))
RANGE_LINE = {
    "set": "v2",
    "target": "m::f",
    "seed": {"s": "a"},
    "status": "differs",
    "only_legacy": [],
    "only_v2": [5],
    "varies": {"only_legacy": [], "only_v2": [4, 6]},
}


def a_file(tmp_path: Path, *lines: str) -> Path:
    file = tmp_path / "accepted.jsonl"
    file.write_text("".join(f"{line}\n" for line in (HEADER, *lines)))
    return file


def showing(*only_v2: int, legacy: SideView = QUICK) -> Row:
    """The row with these lines only v2 covered: ``same`` when there are none."""
    status = Status.DIFFERS if only_v2 else Status.SAME
    return replace(ROW, status=status, only_v2=only_v2, legacy=legacy)


def accepting(record: Record) -> Accepted:
    return Accepted(
        path=Path("/unused"),
        records={record.key: record},
        accept=True,
        listed=frozenset({record.key}),
    )


@pytest.mark.parametrize("only_v2", [(5,), (4, 5), (4, 5, 6), (5, 6)])
def test_a_row_inside_the_range_is_accepted(only_v2: tuple[int, ...]) -> None:
    """keep-a-budget-bound-compare-row-stable-passes-a-seen-outcome"""
    marked = mark(showing(*only_v2), {RANGE.key: RANGE}, ROOTS)

    assert (marked.record, marked.change) == ("accepted", None)
    assert passes(marked)


@pytest.mark.parametrize(("only_v2", "now"), [((4, 6), "4, 6"), ((5, 7), "5, 7"), ((), "none")])
def test_a_row_outside_the_range_is_changed_naming_the_range(
    only_v2: tuple[int, ...], now: str
) -> None:
    """keep-a-budget-bound-compare-row-stable-fails-an-outcome-outside-the-range"""
    for legacy in (QUICK, SPENT):
        marked = mark(showing(*only_v2, legacy=legacy), {RANGE.key: RANGE}, ROOTS)

        assert marked.record == "changed"
        assert f"only v2 was 5 and any of 4, 6, now {now}" in str(marked.change)
        assert not passes(marked)


def test_a_same_row_matches_a_range_with_no_line_every_run_showed() -> None:
    """keep-a-budget-bound-compare-row-stable-a-same-row-inside-the-range-passes"""
    record = replace(EXACT, only_v2=(), varies=Varies(only_v2=(67,)))

    marked = mark(showing(), {record.key: record}, ROOTS)

    assert (marked.record, marked.change) == ("accepted", None)
    assert rewritten(accepting(record), [showing()], ROOTS, BUDGET) == [record]
    assert mark(showing(67), {record.key: record}, ROOTS).record == "accepted"
    closed = mark(showing(), {EXACT.key: EXACT}, ROOTS)
    assert closed.change == "status was differs, now same; only v2 was 5, now none"


def test_a_range_with_a_line_every_run_showed_names_the_status_when_the_row_is_same() -> None:
    marked = mark(showing(), {RANGE.key: RANGE}, ROOTS)

    assert marked.change == "status was differs, now same; only v2 was 5 and any of 4, 6, now none"


def test_the_range_reads_any_of_when_no_line_every_run_showed() -> None:
    record = replace(EXACT, only_v2=(), varies=Varies(only_v2=(4,)))

    assert mark(showing(7), {record.key: record}, ROOTS).change == ("only v2 was any of 4, now 7")


def test_accept_keeps_a_record_the_row_matches_as_it_was() -> None:
    """keep-a-budget-bound-compare-row-stable-accept-keeps-a-matching-record"""
    for record, row in ((RANGE, showing(4, 5, legacy=SPENT)), (EXACT, showing(5, legacy=SPENT))):
        assert rewritten(accepting(record), [row], ROOTS, BUDGET) == [record]


def test_accept_widens_a_record_when_a_side_ran_its_whole_budget() -> None:
    """keep-a-budget-bound-compare-row-stable-accept-widens-a-budget-bound-record"""
    (widened,) = rewritten(accepting(EXACT), [showing(4, 5, 6, legacy=SPENT)], ROOTS, BUDGET)

    assert widened == RANGE
    assert mark(showing(5), {widened.key: widened}, ROOTS).record == "accepted"
    (again,) = rewritten(accepting(widened), [showing(3, legacy=SPENT)], ROOTS, BUDGET)
    assert again == replace(EXACT, only_v2=(), varies=Varies(only_v2=(3, 4, 5, 6)))


def test_a_side_that_ran_exactly_the_budget_ran_all_of_it() -> None:
    at_budget = replace(QUICK, seconds=BUDGET)

    (widened,) = rewritten(accepting(EXACT), [showing(4, 5, legacy=at_budget)], ROOTS, BUDGET)

    assert widened.varies == Varies(only_v2=(4,))


def test_a_same_row_that_ran_its_whole_budget_widens_to_no_line_every_run_showed() -> None:
    """keep-a-budget-bound-compare-row-stable-a-same-budget-bound-row-widens"""
    record = replace(EXACT, only_v2=(67,))

    (widened,) = rewritten(accepting(record), [showing(legacy=SPENT)], ROOTS, BUDGET)

    assert widened == replace(record, only_v2=(), varies=Varies(only_v2=(67,)))


def test_a_row_inside_its_budget_replaces_a_record_it_does_not_match() -> None:
    """keep-a-budget-bound-compare-row-stable-a-row-inside-its-budget-is-replaced"""
    (replaced,) = rewritten(accepting(RANGE), [showing(7)], ROOTS, BUDGET)

    assert replaced == replace(EXACT, only_v2=(7,))
    assert rewritten(accepting(RANGE), [replace(showing(), v2=None)], ROOTS, BUDGET) == []


def test_a_failed_row_replaces_a_range_even_when_a_side_ran_its_whole_budget() -> None:
    failed = replace(
        showing(legacy=replace(SPENT, failure="error: boom")), status=Status.LEGACY_FAILED
    )

    (replaced,) = rewritten(accepting(RANGE), [failed], ROOTS, BUDGET)

    assert (replaced.status, replaced.varies) == ("legacy failed", Varies())


def test_a_failed_record_is_replaced_not_widened_by_a_row_that_ran_its_whole_budget() -> None:
    failed = replace(EXACT, status="legacy failed", only_v2=(), failures={"legacy": "error: boom"})

    (replaced,) = rewritten(accepting(failed), [showing(5, legacy=SPENT)], ROOTS, BUDGET)

    assert replaced == EXACT


def test_a_range_is_written_after_the_lines_and_read_back(tmp_path: Path) -> None:
    file = tmp_path / "accepted.jsonl"

    write_records(file, LIMITS, [RANGE, EXACT])

    lines = file.read_text().splitlines()
    assert json.loads(lines[1]) == RANGE_LINE
    assert list(json.loads(lines[1])) == list(RANGE_LINE)
    assert "varies" not in json.loads(lines[2])
    assert read_records(a_file(tmp_path, lines[1]), False, LIMITS) == {RANGE.key: RANGE}


@pytest.mark.parametrize(
    "varies",
    [
        [4, 6],
        {"only_v2": [4, 6]},
        {"only_legacy": [], "only_v2": "4"},
        {"only_legacy": [], "only_v2": [4.0]},
        {"only_legacy": [], "only_v2": [5]},
    ],
)
def test_a_range_that_is_not_two_lists_of_new_lines_is_refused(
    tmp_path: Path, varies: object
) -> None:
    """keep-a-budget-bound-compare-row-stable-refuses-a-malformed-range"""
    file = a_file(tmp_path, json.dumps({**RANGE_LINE, "varies": varies}))

    with pytest.raises(RecordsError, match=rf"--accepted: {file} line 2 is not a record"):
        read_records(file, False, LIMITS)


def test_a_range_on_a_failed_record_is_refused(tmp_path: Path) -> None:
    failed = {**RANGE_LINE, "status": "legacy failed", "failures": {"legacy": "x"}, "covered": []}
    file = a_file(tmp_path, json.dumps(failed))

    with pytest.raises(RecordsError, match=rf"--accepted: {file} line 2 is not a record"):
        read_records(file, False, LIMITS)

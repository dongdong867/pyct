"""The accepted file: reading records, marking rows against them, and rewriting the file."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from tools.compare_coverage.accepted import (
    Accepted,
    Record,
    RecordsError,
    check_writable,
    key_of,
    mark,
    passes,
    read_records,
    rewritten,
    write_records,
)
from tools.compare_coverage.entries import Origin
from tools.compare_coverage.reasons import stable_reason
from tools.compare_coverage.rows import Row, SideView, Status
from tools.compare_coverage.sides import Limits

DIFFERS = Row(
    set="v2",
    status=Status.DIFFERS,
    file="/t.py",
    target="m::f",
    seed={"x": 0},
    only_legacy=(4,),
    only_v2=(),
)
RECORD = Record(
    set="v2", target="m::f", seed={"x": 0}, status="differs", only_legacy=(4,), only_v2=()
)
LINE = {
    "set": "v2",
    "target": "m::f",
    "seed": {"x": 0},
    "status": "differs",
    "only_legacy": [4],
    "only_v2": [],
}
LIMITS = Limits(budget=5.0, plateau=5, solver_timeout=10.0)
ROOTS = {Origin.V2: Path("/work/v2"), Origin.LEGACY: Path("/work/legacy")}
HEADER = json.dumps({"budget": 5.0, "plateau": 5, "solver_timeout": 10.0})


def a_file(tmp_path: Path, *lines: str, header: str = HEADER) -> Path:
    """An accepted file: its limits line, then ``lines``."""
    file = tmp_path / "accepted.jsonl"
    file.write_text("".join(f"{line}\n" for line in (header, *lines)))
    return file


V2_RAN = SideView(file="/t.py", covered=(2, 3, 4), stopped="done", inputs=2, failure=None)
LEGACY_FAILED = SideView(file=None, covered=(), stopped=None, inputs=None, failure="error: boom")
FAILED = Row(
    set="v2",
    status=Status.LEGACY_FAILED,
    file="/t.py",
    target="m::f",
    seed={"x": 0},
    v2=V2_RAN,
    legacy=LEGACY_FAILED,
)
FAILED_RECORD = Record(
    set="v2",
    target="m::f",
    seed={"x": 0},
    status="legacy failed",
    only_legacy=(),
    only_v2=(),
    failures={"legacy": "error: boom"},
    covered=(2, 3, 4),
)
FAILED_LINE = {
    **LINE,
    "status": "legacy failed",
    "only_legacy": [],
    "failures": {"legacy": "error: boom"},
    "covered": [2, 3, 4],
}


def test_a_failed_row_is_recorded_with_its_reasons_and_what_the_other_side_covered(
    tmp_path: Path,
) -> None:
    file = tmp_path / "accepted.jsonl"
    accepted = Accepted(path=file, records={}, accept=True, listed=frozenset())

    records = rewritten(accepted, [FAILED], ROOTS)
    write_records(file, LIMITS, records)

    assert records == [FAILED_RECORD]
    assert json.loads(file.read_text().splitlines()[1]) == FAILED_LINE
    assert read_records(file, False, LIMITS) == {FAILED_RECORD.key: FAILED_RECORD}


def test_both_sides_failing_records_both_reasons_and_no_lines() -> None:
    v2_failed = replace(V2_RAN, covered=(), failure="exit 2: refused")
    both = replace(FAILED, status=Status.BOTH_FAILED, v2=v2_failed)
    accepted = Accepted(path=Path("/unused"), records={}, accept=True, listed=frozenset())

    (record,) = rewritten(accepted, [both], ROOTS)

    assert record.failures == {"v2": "exit 2: refused", "legacy": "error: boom"}
    assert record.covered == ()


def test_a_reason_is_recorded_without_what_changes_between_runs() -> None:
    reason = (
        "exit 1: TypeError: Cannot isolate target <function deco.<locals>.wrapper at 0x108b01b2f>"
        " — loaded /usr/lib/python3.12/shutil.py, the entry names /work/v2/targets/t.py"
        " in /work/legacy/tests/x.py, not /work/legacy, 3/4 of /work/v2x/y.py"
    )

    assert stable_reason(reason, ROOTS) == (
        "exit 1: TypeError: Cannot isolate target <function deco.<locals>.wrapper at <address>>"
        " — loaded <elsewhere>/shutil.py, the entry names <v2>/targets/t.py"
        " in <legacy>/tests/x.py, not <legacy>, 3/4 of <elsewhere>/y.py"
    )


def test_a_failed_row_matches_a_record_made_at_another_address_and_place() -> None:
    elsewhere = {Origin.V2: Path("/other/v2"), Origin.LEGACY: Path("/other/legacy")}
    at = replace(LEGACY_FAILED, failure="error: <object at 0xabc> in /work/legacy/src/a.py")
    accepted = Accepted(path=Path("/unused"), records={}, accept=True, listed=frozenset())
    (record,) = rewritten(accepted, [replace(FAILED, legacy=at)], ROOTS)
    moved = replace(LEGACY_FAILED, failure="error: <object at 0xdef> in /other/legacy/src/a.py")

    marked = mark(replace(FAILED, legacy=moved), {record.key: record}, elsewhere)

    assert record.failures == {"legacy": "error: <object at <address>> in <legacy>/src/a.py"}
    assert (marked.record, marked.change) == ("accepted", None)
    # the row itself keeps the text as the side gave it
    assert marked.legacy == moved


def test_a_failed_row_that_failed_the_same_way_is_accepted() -> None:
    assert mark(FAILED, {FAILED_RECORD.key: FAILED_RECORD}, ROOTS).record == "accepted"


def test_a_failed_row_whose_other_side_lost_a_line_is_changed() -> None:
    lost = replace(FAILED, v2=replace(V2_RAN, covered=(2, 3)))

    marked = mark(lost, {FAILED_RECORD.key: FAILED_RECORD}, ROOTS)

    assert marked.record == "changed"
    assert marked.change == "v2 covered was 2, 3, 4, now 2, 3"


def test_a_failed_row_with_another_reason_is_changed_naming_both() -> None:
    other = replace(FAILED, legacy=replace(LEGACY_FAILED, failure="error: bang"))

    marked = mark(other, {FAILED_RECORD.key: FAILED_RECORD}, ROOTS)

    assert marked.record == "changed"
    assert marked.change == "legacy failure was 'error: boom', now 'error: bang'"


def test_a_failed_row_that_now_runs_names_what_changed_without_naming_a_side() -> None:
    same = Row(set="v2", status=Status.SAME, file="/t.py", target="m::f", seed={"x": 0})

    marked = mark(same, {FAILED_RECORD.key: FAILED_RECORD}, ROOTS)

    assert marked.change == (
        "status was legacy failed, now same; legacy failure was 'error: boom', now none; "
        "the side that ran covered was 2, 3, 4, now none"
    )


def test_a_failed_record_without_its_reasons_or_lines_is_refused(tmp_path: Path) -> None:
    file = a_file(tmp_path, json.dumps({**LINE, "status": "v2 failed"}))

    with pytest.raises(RecordsError, match="line 2 is not a record"):
        read_records(file, False, LIMITS)


def test_a_record_is_found_by_its_target_and_canonical_seed() -> None:
    assert key_of("m::f", {"b": 1, "a": 2}) == key_of("m::f", {"a": 2, "b": 1})
    assert RECORD.key == ("m::f", '{"x": 0}')


def test_records_are_read_one_per_line_after_the_limits(tmp_path: Path) -> None:
    file = a_file(tmp_path, json.dumps(LINE))

    assert read_records(file, False, LIMITS) == {RECORD.key: RECORD}


def test_a_file_made_with_other_limits_is_refused_naming_both(tmp_path: Path) -> None:
    file = a_file(tmp_path, json.dumps(LINE))

    with pytest.raises(
        RecordsError,
        match=rf"--accepted: {file} was made with budget 5 s, plateau 5, solver timeout 10 s; "
        "this run has budget 30 s, plateau 5, solver timeout 10 s",
    ):
        read_records(file, True, Limits(budget=30.0))


@pytest.mark.parametrize(
    "header",
    [
        json.dumps(LINE),
        "",
        json.dumps({"budget": 5.0, "plateau": 5}),
        json.dumps({"budget": "5", "plateau": 5, "solver_timeout": 10.0}),
        json.dumps({"budget": 5.0, "plateau": True, "solver_timeout": 10.0}),
        json.dumps([5.0, 5, 10.0]),
    ],
)
def test_a_file_whose_first_line_is_not_its_limits_is_refused(tmp_path: Path, header: str) -> None:
    file = a_file(tmp_path, header=header)

    with pytest.raises(RecordsError, match=rf"{file} line 1 does not record the limits"):
        read_records(file, True, LIMITS)


def test_a_missing_file_holds_no_records_only_when_accepting(tmp_path: Path) -> None:
    missing = tmp_path / "accepted.jsonl"

    assert read_records(missing, True, LIMITS) == {}
    with pytest.raises(RecordsError, match=rf"--accepted: cannot read {missing}: no such file"):
        read_records(missing, False, LIMITS)


def test_a_file_accept_writes_needs_a_folder_it_can_write(tmp_path: Path) -> None:
    missing = tmp_path / "no-folder" / "accepted.jsonl"
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    read_only = tmp_path / "read-only.jsonl"
    read_only.write_text("")
    read_only.chmod(0o400)

    check_writable(tmp_path / "accepted.jsonl")
    with pytest.raises(RecordsError, match=rf"cannot write {missing}: no folder {missing.parent}"):
        check_writable(missing)
    with pytest.raises(RecordsError, match=rf"cannot write {locked}/a.jsonl: permission denied"):
        check_writable(locked / "a.jsonl")
    with pytest.raises(RecordsError, match=rf"cannot write {read_only}: permission denied"):
        check_writable(read_only)
    locked.chmod(0o700)


def test_a_file_that_cannot_be_read_is_refused(tmp_path: Path) -> None:
    with pytest.raises(RecordsError, match=rf"--accepted: cannot read {tmp_path}"):
        read_records(tmp_path, True, LIMITS)


@pytest.mark.parametrize(
    "line",
    [
        "not json",
        json.dumps([1]),
        json.dumps({**LINE, "status": "fine"}),
        json.dumps({key: value for key, value in LINE.items() if key != "only_v2"}),
        json.dumps({**LINE, "seed": [0]}),
        json.dumps({**LINE, "target": 5}),
        json.dumps({**LINE, "only_legacy": ["4"]}),
    ],
)
def test_a_line_that_is_not_a_record_is_refused_naming_it(tmp_path: Path, line: str) -> None:
    file = a_file(tmp_path, json.dumps(LINE), line)

    with pytest.raises(RecordsError, match=rf"--accepted: {file} line 3 is not a record"):
        read_records(file, False, LIMITS)


def test_two_records_for_one_target_and_seed_are_refused_naming_both(tmp_path: Path) -> None:
    other, again = json.dumps({**LINE, "target": "m::g"}), json.dumps({**LINE, "only_legacy": [5]})
    file = a_file(tmp_path, json.dumps(LINE), other, again)

    with pytest.raises(RecordsError, match=rf"--accepted: {file} lines 2 and 4 record m::f"):
        read_records(file, False, LIMITS)


def test_a_row_that_matches_its_record_is_accepted_and_passes() -> None:
    marked = mark(DIFFERS, {RECORD.key: RECORD}, ROOTS)

    assert (marked.record, marked.change) == ("accepted", None)
    assert passes(marked)


def test_a_row_that_moved_is_changed_names_what_moved_and_fails() -> None:
    now = replace(DIFFERS, only_legacy=(4, 9), only_v2=(3,))

    marked = mark(now, {RECORD.key: RECORD}, ROOTS)

    assert marked.record == "changed"
    assert marked.change == "only legacy was 4, now 4, 9; only v2 was none, now 3"
    assert not passes(marked)


def test_a_closed_gap_is_a_change() -> None:
    closed = replace(DIFFERS, status=Status.SAME, only_legacy=())

    marked = mark(closed, {RECORD.key: RECORD}, ROOTS)

    assert marked.change == "status was differs, now same; only legacy was 4, now none"
    assert not passes(marked)


def test_a_row_without_a_record_passes_only_as_same_or_left_out() -> None:
    assert mark(DIFFERS, {}, ROOTS) == DIFFERS
    assert not passes(DIFFERS)
    assert passes(replace(DIFFERS, status=Status.SAME))
    left = Row(set="v2", status=Status.LEFT_OUT, file="/t.py", left_out="why")
    assert mark(left, {RECORD.key: RECORD}, ROOTS) == left
    assert passes(left)
    assert not passes(Row(set="v2", status=Status.NOT_LISTED, file="/u.py"))


def test_a_rewrite_replaces_run_rows_keeps_the_rest_and_drops_the_gone() -> None:
    kept = replace(RECORD, target="a::kept")
    gone = replace(RECORD, target="z::gone")
    closed = replace(RECORD, target="m::closed")
    listed = frozenset({RECORD.key, kept.key, closed.key})
    accepted = Accepted(
        path=Path("/unused"),
        records={record.key: record for record in (RECORD, kept, gone, closed)},
        accept=True,
        listed=listed,
    )
    rows = [
        replace(DIFFERS, only_legacy=(5,)),
        replace(DIFFERS, target="m::closed", status=Status.SAME, only_legacy=()),
        Row(set="v2", status=Status.NOT_LISTED, file="/u.py"),
        replace(DIFFERS, set="fixtures", target="b::new", status=Status.V2_FAILED, only_legacy=()),
    ]

    records = rewritten(accepted, rows, ROOTS)

    assert records == [
        replace(RECORD, set="fixtures", target="b::new", status="v2 failed", only_legacy=()),
        kept,
        replace(RECORD, only_legacy=(5,)),
    ]


def test_records_are_written_one_per_line_after_the_limits(tmp_path: Path) -> None:
    file = tmp_path / "accepted.jsonl"

    write_records(file, LIMITS, [RECORD, RECORD])

    assert file.read_text() == f"{HEADER}\n" + 2 * (json.dumps(LINE) + "\n")

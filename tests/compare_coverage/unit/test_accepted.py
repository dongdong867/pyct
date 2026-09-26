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
from tools.compare_coverage.rows import Row, Status

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


def test_a_record_is_found_by_its_target_and_canonical_seed() -> None:
    assert key_of("m::f", {"b": 1, "a": 2}) == key_of("m::f", {"a": 2, "b": 1})
    assert RECORD.key == ("m::f", '{"x": 0}')


def test_records_are_read_one_per_line(tmp_path: Path) -> None:
    file = tmp_path / "accepted.jsonl"
    file.write_text(json.dumps(LINE) + "\n")

    assert read_records(file, accept=False) == {RECORD.key: RECORD}


def test_a_missing_file_holds_no_records_only_when_accepting(tmp_path: Path) -> None:
    missing = tmp_path / "accepted.jsonl"

    assert read_records(missing, accept=True) == {}
    with pytest.raises(RecordsError, match=rf"--accepted: cannot read {missing}: no such file"):
        read_records(missing, accept=False)


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
        read_records(tmp_path, accept=True)


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
    file = tmp_path / "accepted.jsonl"
    file.write_text(json.dumps(LINE) + "\n" + line + "\n")

    with pytest.raises(RecordsError, match=rf"--accepted: {file} line 2 is not a record"):
        read_records(file, accept=False)


def test_a_row_that_matches_its_record_is_accepted_and_passes() -> None:
    marked = mark(DIFFERS, {RECORD.key: RECORD})

    assert (marked.record, marked.change) == ("accepted", None)
    assert passes(marked)


def test_a_row_that_moved_is_changed_names_what_moved_and_fails() -> None:
    now = replace(DIFFERS, only_legacy=(4, 9), only_v2=(3,))

    marked = mark(now, {RECORD.key: RECORD})

    assert marked.record == "changed"
    assert marked.change == "only legacy was 4, now 4, 9; only v2 was none, now 3"
    assert not passes(marked)


def test_a_closed_gap_is_a_change() -> None:
    closed = replace(DIFFERS, status=Status.SAME, only_legacy=())

    marked = mark(closed, {RECORD.key: RECORD})

    assert marked.change == "status was differs, now same; only legacy was 4, now none"
    assert not passes(marked)


def test_a_row_without_a_record_passes_only_as_same_or_left_out() -> None:
    assert mark(DIFFERS, {}) == DIFFERS
    assert not passes(DIFFERS)
    assert passes(replace(DIFFERS, status=Status.SAME))
    left = Row(set="v2", status=Status.LEFT_OUT, file="/t.py", left_out="why")
    assert mark(left, {RECORD.key: RECORD}) == left
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

    records = rewritten(accepted, rows)

    assert records == [
        replace(RECORD, set="fixtures", target="b::new", status="v2 failed", only_legacy=()),
        kept,
        replace(RECORD, only_legacy=(5,)),
    ]


def test_records_are_written_one_per_line_in_the_records_key_order(tmp_path: Path) -> None:
    file = tmp_path / "accepted.jsonl"

    write_records(file, [RECORD, RECORD])

    assert file.read_text() == 2 * (json.dumps(LINE) + "\n")

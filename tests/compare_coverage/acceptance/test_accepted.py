"""Acceptance tests for compare-coverage-on-the-fixtures: the file of accepted differences.

Legacy is the stub engine here, so a difference is exact; v2 is the real ``pyct run``. The
committed seed of ``one_check`` covers lines 2, 3 and 4 in v2.
"""

from pathlib import Path

from tests.compare_coverage.acceptance.checker import (
    IMPLIED_CHECK,
    ONE_CHECK,
    TWO_ARGS,
    one_row,
    read_records,
    rows,
    run_checker,
    table_rows,
    write_records,
)
from tests.compare_coverage.conftest import StubCheckout

# a gap v2 has since closed: legacy covered line 4 and v2 did not
ONE_CHECK_GAP = {
    "set": "v2",
    "target": ONE_CHECK,
    "seed": {"x": 0},
    "status": "differs",
    "only_legacy": [4],
    "only_v2": [],
}
# the unreachable line 5, which the stub says legacy covers
IMPLIED_GAP = {
    "set": "v2",
    "target": IMPLIED_CHECK,
    "seed": {"x": 3},
    "status": "differs",
    "only_legacy": [5],
    "only_v2": [],
}
TWO_ARGS_GAP = {
    "set": "v2",
    "target": TWO_ARGS,
    "seed": {"x": 3, "y": 7},
    "status": "differs",
    "only_legacy": [3],
    "only_v2": [],
}


def test_accepts_the_new_state(stub_checkout: StubCheckout, tmp_path: Path) -> None:
    """compare-coverage-against-legacy-accepts-the-new-state"""
    stub_checkout.script({ONE_CHECK: {"lines": [2, 3, 4]}})
    accepted = tmp_path / "accepted.jsonl"
    # out of order, so the rewrite has to sort what it keeps
    write_records(accepted, TWO_ARGS_GAP, ONE_CHECK_GAP, IMPLIED_GAP)
    legacy = ("--legacy", str(stub_checkout.path))

    result = run_checker(*legacy, "--target", ONE_CHECK, "--accepted", str(accepted), "--accept")

    row = one_row(result.stdout)
    assert row["status"] == "same"
    assert row["record"] == "changed"
    assert read_records(accepted) == [IMPLIED_GAP, TWO_ARGS_GAP]
    assert result.returncode == 0, result.stderr

    again = run_checker(*legacy, "--target", ONE_CHECK, "--accepted", str(accepted))

    assert one_row(again.stdout)["record"] is None
    assert again.returncode == 0, again.stderr


def test_passes_a_recorded_difference(stub_checkout: StubCheckout, tmp_path: Path) -> None:
    """compare-coverage-against-legacy-passes-a-recorded-difference"""
    stub_checkout.script(
        {IMPLIED_CHECK: {"lines": [2, 3, 4, 5, 6]}, ONE_CHECK: {"lines": [2, 3, 4]}}
    )
    accepted = tmp_path / "accepted.jsonl"
    write_records(accepted, IMPLIED_GAP)

    result = run_checker(
        *("--legacy", str(stub_checkout.path), "--accepted", str(accepted)),
        *("--target", IMPLIED_CHECK, "--target", ONE_CHECK),
    )

    implied, one_check = rows(result.stdout)
    assert implied["status"] == "differs"
    assert implied["record"] == "accepted"
    assert one_check["status"] == "same"
    (line,) = table_rows(result.stderr, IMPLIED_CHECK)
    assert "accepted" in line
    assert result.returncode == 0, result.stderr


def test_fails_a_changed_row(stub_checkout: StubCheckout, tmp_path: Path) -> None:
    """compare-coverage-against-legacy-fails-a-changed-row"""
    stub_checkout.script({ONE_CHECK: {"lines": [2, 3, 4]}})
    accepted = tmp_path / "accepted.jsonl"
    write_records(accepted, ONE_CHECK_GAP)

    result = run_checker(
        "--legacy", str(stub_checkout.path), "--target", ONE_CHECK, "--accepted", str(accepted)
    )

    row = one_row(result.stdout)
    assert row["record"] == "changed"
    assert "4" in row["change"]
    (line,) = table_rows(result.stderr, ONE_CHECK)
    assert "changed" in line
    assert "4" in line.split("changed", 1)[1]
    assert read_records(accepted) == [ONE_CHECK_GAP]
    assert result.returncode == 1

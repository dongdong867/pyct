"""Acceptance tests for compare-coverage-on-the-fixtures: the file of accepted differences.

Legacy is the stub engine here, so a difference is exact; v2 is the real ``pyct run``. The
committed seed of ``one_check`` covers lines 2, 3 and 4 in v2.
"""

import json
import os
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from tests.compare_coverage.acceptance.checker import (
    DEFAULT_LIMITS,
    IMPLIED_CHECK,
    ONE_CHECK,
    ONE_CHECK_FILE,
    REPO_ROOT,
    TWO_ARGS,
    a_run,
    compare_on,
    legacy_side,
    one_row,
    read_limits,
    read_records,
    rows,
    run_checker,
    table_rows,
    write_records,
)
from tests.compare_coverage.conftest import StubCheckout
from tools.compare_coverage.accepted import Accepted, key_of
from tools.compare_coverage.accepted import read_records as read_file
from tools.compare_coverage.compare import Sides
from tools.compare_coverage.entries import Entry, Origin
from tools.compare_coverage.process import side_environment
from tools.compare_coverage.v2_side import Stamp, V2Side

type Row = dict[str, Any]

ONE_CHECK_ENTRY = Entry(set="v2", module="targets.flip.one_check", name="classify", seed={"x": 0})

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

    row = one_row(result.stdout, result.stderr)
    assert row["status"] == "same"
    assert row["record"] == "changed"
    assert read_limits(accepted) == DEFAULT_LIMITS
    assert read_records(accepted) == [IMPLIED_GAP, TWO_ARGS_GAP]
    assert result.returncode == 0, result.stderr

    again = run_checker(*legacy, "--target", ONE_CHECK, "--accepted", str(accepted))

    assert one_row(again.stdout, again.stderr)["record"] is None
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

    implied, one_check = rows(result.stdout, result.stderr)
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

    row = one_row(result.stdout, result.stderr)
    change = "status was differs, now same; only legacy was 4, now none"
    assert row["record"] == "changed"
    assert row["change"] == change
    (line,) = table_rows(result.stderr, ONE_CHECK)
    assert line.endswith(f"same, changed  changed: {change}")
    assert read_records(accepted) == [ONE_CHECK_GAP]
    assert result.returncode == 1


# stands in for pyct run: a summary line covering the lines in LINES_FILE, stamped as here
COVERS = """\
import json, os, platform
lines = json.load(open(os.environ["LINES_FILE"]))
print(json.dumps({
    "stopped": "no fork to flip",
    "inputs": 2,
    "covered": {%r: lines},
    "environment": {"python": platform.python_version(), "platform": platform.platform()},
}))
"""


class LegacyFails:
    """One_check through compare(), with legacy's error and the lines a fake v2 covers set."""

    def __init__(self, stub: StubCheckout, tmp_path: Path) -> None:
        fake = tmp_path / "fake_pyct.py"
        fake.write_text(COVERS % ONE_CHECK_FILE)
        self.lines = tmp_path / "lines.json"
        environment = {**side_environment(os.environ), "LINES_FILE": str(self.lines)}
        program = (sys.executable, str(fake))
        v2 = V2Side(program=program, environment=environment, stamp=Stamp.here())
        self.sides = Sides(v2=v2, legacy=legacy_side(stub.path))
        self.stub = stub
        self.file = tmp_path / "accepted.jsonl"
        self.roots = {Origin.V2: REPO_ROOT, Origin.LEGACY: stub.path}

    def run(self, v2_lines: list[int], error: str, accept: bool = False) -> tuple[int, Row]:
        self.lines.write_text(json.dumps(v2_lines))
        self.stub.script({ONE_CHECK: {"success": False, "stopped": "error", "error": error}})
        run = a_run([ONE_CHECK_ENTRY], self.roots)
        records = read_file(self.file, accept, run.limits)
        listed = frozenset({key_of(ONE_CHECK, {"x": 0})})
        accepted = Accepted(path=self.file, records=records, accept=accept, listed=listed)
        run = replace(run, accepted=accepted)
        code, (row,), _ = compare_on(run, self.sides)
        return code, row


def test_fails_a_changed_failure(stub_checkout: StubCheckout, tmp_path: Path) -> None:
    """compare-coverage-against-legacy-fails-a-changed-failure"""
    legacy_fails = LegacyFails(stub_checkout, tmp_path)

    legacy_fails.run([2, 3, 4], "boom", accept=True)

    assert read_records(legacy_fails.file) == [
        ONE_CHECK_GAP
        | {"status": "legacy failed", "only_legacy": []}
        | {"failures": {"legacy": "error: boom"}, "covered": [2, 3, 4]}
    ]
    code, again = legacy_fails.run([2, 3, 4], "boom")
    assert (code, again["record"]) == (0, "accepted")
    code, lost = legacy_fails.run([2, 3], "boom")
    assert (code, lost["record"], lost["change"]) == (
        1,
        "changed",
        "v2 covered was 2, 3, 4, now 2, 3",
    )
    code, other = legacy_fails.run([2, 3, 4], "bang")
    assert (code, other["record"], other["change"]) == (
        1,
        "changed",
        "legacy failure was 'error: boom', now 'error: bang'",
    )


def test_refuses_a_file_made_with_other_limits(stub_checkout: StubCheckout, tmp_path: Path) -> None:
    """compare-coverage-against-legacy-refuses-a-file-made-with-other-limits"""
    stub_checkout.script({IMPLIED_CHECK: {"lines": [2, 3, 4, 5, 6]}})
    accepted = tmp_path / "accepted.jsonl"
    five = {"budget": 5.0, "plateau": 5, "solver_timeout": 10.0}
    write_records(accepted, IMPLIED_GAP, limits=five)
    written = accepted.read_text()
    command = ("--legacy", str(stub_checkout.path), "--target", IMPLIED_CHECK)

    for accept in ([], ["--accept"]):
        result = run_checker(*command, "--accepted", str(accepted), *accept)

        assert (
            f"--accepted: {accepted} was made with budget 5 s, plateau 5, solver timeout 10 s; "
            "this run has budget 30 s, plateau 5, solver timeout 10 s"
        ) in result.stderr
        assert result.stdout == ""
        assert accepted.read_text() == written
        assert result.returncode == 2

    result = run_checker(*command, "--accepted", str(accepted), "--budget", "5")

    assert one_row(result.stdout, result.stderr)["record"] == "accepted"
    assert result.returncode == 0, result.stderr

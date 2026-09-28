"""Acceptance tests for keep-a-budget-bound-compare-row-stable: a row that varies with its budget.

v2 is a fake ``pyct run`` that covers lines 2, 3 and 4 of ``one_check`` at once, and legacy is
the stub engine, so each row's lines are exact. A stub ``sleep`` past a 1 s budget makes the
legacy side run its whole budget; without it, both sides end well inside a 10 s one.
"""

import os
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from tests.compare_coverage.acceptance.checker import (
    ONE_CHECK,
    ONE_CHECK_ENTRY,
    ONE_CHECK_FILE,
    a_run,
    compare_on,
    legacy_side,
    one_row,
    read_records,
    roots,
    run_checker,
    table_rows,
    write_records,
)
from tests.compare_coverage.conftest import StubCheckout
from tools.compare_coverage.accepted import Accepted, key_of
from tools.compare_coverage.accepted import read_records as read_file
from tools.compare_coverage.compare import Sides
from tools.compare_coverage.process import side_environment
from tools.compare_coverage.sides import Limits
from tools.compare_coverage.v2_side import Stamp, V2Side

type Row = dict[str, Any]

# stands in for pyct run: a summary line covering lines 2, 3 and 4 of one_check, stamped as here
COVERS = """\
import json, platform
print(json.dumps({
    "stopped": "no fork to flip",
    "inputs": 2,
    "covered": {%r: [2, 3, 4]},
    "environment": {"python": platform.python_version(), "platform": platform.platform()},
}))
"""

# legacy covering 2 and 3 leaves 4 only v2's; covering 2 alone leaves 3 and 4
FOUR = {"set": "v2", "target": ONE_CHECK, "seed": {"x": 0}, "status": "differs"}
FOUR = FOUR | {"only_legacy": [], "only_v2": [4]}
FOUR_OR_THREE = FOUR | {"varies": {"only_legacy": [], "only_v2": [3]}}

SPENT = Limits(budget=1.0)
INSIDE = Limits(budget=10.0)


class Checker:
    """one_check through compare(), with the lines legacy covers and how long it takes set."""

    def __init__(self, stub: StubCheckout, tmp_path: Path) -> None:
        fake = tmp_path / "fake_pyct.py"
        fake.write_text(COVERS % ONE_CHECK_FILE)
        environment = side_environment(os.environ)
        v2 = V2Side(
            program=(sys.executable, str(fake)), environment=environment, stamp=Stamp.here()
        )
        self.sides = Sides(v2=v2, legacy=legacy_side(stub.path))
        self.stub = stub
        self.file = tmp_path / "accepted.jsonl"
        self.roots = roots(stub.path)

    def run(self, legacy_lines: list[int], limits: Limits, accept: bool = False) -> tuple[int, Row]:
        """The exit and the row; legacy sleeps past the budget when ``limits`` is ``SPENT``."""
        sleep = 1.2 if limits == SPENT else 0
        self.stub.script({ONE_CHECK: {"lines": legacy_lines, "sleep": sleep}})
        run = a_run([ONE_CHECK_ENTRY], self.roots, limits=limits, grace=30.0)
        records = read_file(self.file, accept, limits)
        listed = frozenset({key_of(ONE_CHECK, {"x": 0})})
        accepted = Accepted(path=self.file, records=records, accept=accept, listed=listed)
        code, (row,), _ = compare_on(replace(run, accepted=accepted), self.sides)
        return code, row

    def records(self, *records: dict[str, Any], limits: Limits) -> None:
        write_records(self.file, *records, limits=limits_line(limits))


def limits_line(limits: Limits) -> dict[str, Any]:
    return {"budget": limits.budget, "plateau": limits.plateau, "solver_timeout": 10.0}


def test_passes_a_seen_outcome(stub_checkout: StubCheckout, tmp_path: Path) -> None:
    """keep-a-budget-bound-compare-row-stable-passes-a-seen-outcome"""
    checker = Checker(stub_checkout, tmp_path)
    checker.records(FOUR_OR_THREE, limits=INSIDE)

    for legacy_lines, only_v2 in (([2, 3], [4]), ([2], [3, 4])):
        code, row = checker.run(legacy_lines, INSIDE)

        assert (row["only_v2"], row["record"], code) == (only_v2, "accepted", 0), row


def test_accept_keeps_a_matching_record(stub_checkout: StubCheckout, tmp_path: Path) -> None:
    """keep-a-budget-bound-compare-row-stable-accept-keeps-a-matching-record"""
    checker = Checker(stub_checkout, tmp_path)

    for record in (FOUR_OR_THREE, FOUR):
        checker.records(record, limits=SPENT)
        written = checker.file.read_text()

        code, row = checker.run([2, 3], SPENT, accept=True)

        assert (row["record"], code) == ("accepted", 0), row
        assert checker.file.read_text() == written


def test_accept_widens_a_budget_bound_record(stub_checkout: StubCheckout, tmp_path: Path) -> None:
    """keep-a-budget-bound-compare-row-stable-accept-widens-a-budget-bound-record"""
    checker = Checker(stub_checkout, tmp_path)
    checker.records(FOUR, limits=SPENT)

    code, row = checker.run([2], SPENT, accept=True)

    assert row["legacy"]["seconds"] >= SPENT.budget
    assert (row["only_v2"], row["record"], code) == ([3, 4], "changed", 0), row
    assert read_records(checker.file) == [FOUR_OR_THREE]
    code, row = checker.run([2, 3], SPENT)
    assert (row["record"], code) == ("accepted", 0), row


def test_a_same_row_inside_the_range_passes(stub_checkout: StubCheckout, tmp_path: Path) -> None:
    """keep-a-budget-bound-compare-row-stable-a-same-row-inside-the-range-passes"""
    checker = Checker(stub_checkout, tmp_path)
    any_of_four = FOUR | {"only_v2": [], "varies": {"only_legacy": [], "only_v2": [4]}}
    checker.records(any_of_four, limits=INSIDE)
    written = checker.file.read_text()

    code, row = checker.run([2, 3, 4], INSIDE, accept=True)

    assert (row["status"], row["record"], code) == ("same", "accepted", 0), row
    assert checker.file.read_text() == written


def test_a_row_inside_its_budget_is_replaced(stub_checkout: StubCheckout, tmp_path: Path) -> None:
    """keep-a-budget-bound-compare-row-stable-a-row-inside-its-budget-is-replaced"""
    checker = Checker(stub_checkout, tmp_path)
    checker.records(FOUR_OR_THREE, limits=INSIDE)

    code, row = checker.run([3], INSIDE, accept=True)

    assert row["legacy"]["seconds"] < INSIDE.budget
    assert (row["only_v2"], row["record"], code) == ([2, 4], "changed", 0), row
    assert read_records(checker.file) == [FOUR | {"only_v2": [2, 4]}]


def test_a_same_budget_bound_row_widens(stub_checkout: StubCheckout, tmp_path: Path) -> None:
    """keep-a-budget-bound-compare-row-stable-a-same-budget-bound-row-widens"""
    checker = Checker(stub_checkout, tmp_path)
    checker.records(FOUR, limits=SPENT)

    code, row = checker.run([2, 3, 4], SPENT, accept=True)

    assert (row["status"], row["record"], code) == ("same", "changed", 0), row
    widened = FOUR | {"only_v2": [], "varies": {"only_legacy": [], "only_v2": [4]}}
    assert read_records(checker.file) == [widened]


def test_fails_an_outcome_outside_the_range(stub_checkout: StubCheckout, tmp_path: Path) -> None:
    """keep-a-budget-bound-compare-row-stable-fails-an-outcome-outside-the-range"""
    checker = Checker(stub_checkout, tmp_path)

    for limits in (SPENT, INSIDE):
        checker.records(FOUR_OR_THREE, limits=limits)

        code, row = checker.run([], limits)

        assert (row["record"], code) == ("changed", 1), row
        assert row["change"] == "only v2 was 4 and any of 3, now 2, 3, 4"


def test_shows_each_side_s_time(stub_checkout: StubCheckout, tmp_path: Path) -> None:
    """keep-a-budget-bound-compare-row-stable-shows-each-side-s-time"""
    stub_checkout.script({ONE_CHECK: {"lines": [2, 3, 4], "sleep": 0.5}})
    # a git checkout, so the second run reuses the first run's legacy result
    stub_checkout.commit()
    legacy = ("--legacy", str(stub_checkout.path), "--target", ONE_CHECK)

    first, again = run_checker(*legacy), run_checker(*legacy)

    row, reused = one_row(first.stdout, first.stderr), one_row(again.stdout, again.stderr)
    seconds = row["legacy"]["seconds"]
    assert seconds >= 0.5 and seconds == round(seconds, 1)
    assert isinstance(row["v2"]["seconds"], float)
    (line,) = table_rows(first.stderr, ONE_CHECK)
    assert f"inputs, {seconds:.1f} s)" in line
    assert (reused["legacy"]["reused"], reused["legacy"]["seconds"]) == (True, seconds)


def test_refuses_a_malformed_range(stub_checkout: StubCheckout, tmp_path: Path) -> None:
    """keep-a-budget-bound-compare-row-stable-refuses-a-malformed-range"""
    accepted = tmp_path / "accepted.jsonl"
    command = ("--legacy", str(stub_checkout.path), "--target", ONE_CHECK)
    overlapping = FOUR | {"varies": {"only_legacy": [], "only_v2": [4]}}
    failed = {**FOUR_OR_THREE, "status": "v2 failed", "failures": {"v2": "x"}, "covered": []}

    for record in (FOUR | {"varies": [3]}, overlapping, failed):
        write_records(accepted, record)

        result = run_checker(*command, "--accepted", str(accepted))

        assert f"--accepted: {accepted} line 2 is not a record" in result.stderr
        assert (result.stdout, result.returncode) == ("", 2)

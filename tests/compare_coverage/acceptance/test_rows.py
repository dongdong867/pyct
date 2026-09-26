"""Acceptance tests for compare-coverage-on-the-fixtures: rows from real runs of both sides.

Each test runs the checker as a person does, against a real checkout of main built once per
session, on one committed entry. The legacy marker lets ``-m "not legacy"`` skip them; the
timeout marker leaves room for the first test to build the checkout.
"""

from pathlib import Path

import pytest

from tests.compare_coverage.acceptance.checker import (
    ONE_CHECK,
    ONE_CHECK_FILE,
    REPO_ROOT,
    one_row,
    run_checker,
    summary,
    table_rows,
)

pytestmark = [pytest.mark.legacy, pytest.mark.timeout(180)]

COMPARE = REPO_ROOT / "targets" / "compare"


def test_reports_a_matching_target(legacy_checkout: Path) -> None:
    """compare-coverage-against-legacy-reports-a-matching-target"""
    result = run_checker("--legacy", str(legacy_checkout), "--target", ONE_CHECK)

    row = one_row(result.stdout)
    assert row["status"] == "same"
    assert row["seed"] == {"x": 0}
    assert row["file"] == ONE_CHECK_FILE
    assert row["v2"]["covered"] == [2, 3, 4]
    assert row["legacy"]["covered"] == [2, 3, 4]
    assert "statuses" in summary(result.stdout)
    (line,) = table_rows(result.stderr, ONE_CHECK)
    assert "same" in line
    assert result.returncode == 0, result.stderr


def test_lifts_the_legacy_input_cap(legacy_checkout: Path) -> None:
    """compare-coverage-against-legacy-lifts-the-legacy-input-cap"""
    target = "targets.compare.sixty_checks::sixty_checks"

    result = run_checker("--legacy", str(legacy_checkout), "--target", target)

    row = one_row(result.stdout)
    assert row["legacy"]["inputs"] > 50, row
    assert row["legacy"]["stopped"] != "max_iterations", row
    assert row["legacy"]["failure"] is None, row


def test_compares_only_the_target_body(legacy_checkout: Path) -> None:
    """compare-coverage-against-legacy-compares-only-the-target-body"""
    target = "targets.compare.helper_beside::route"

    result = run_checker("--legacy", str(legacy_checkout), "--target", target)

    row = one_row(result.stdout)
    helper_lines = {5, 6, 7}
    assert row["own_lines"] == [11, 12, 13, 14]
    assert not helper_lines & set(row["v2"]["covered"])
    assert not helper_lines & set(row["legacy"]["covered"])
    assert row["v2"]["covered"] == row["legacy"]["covered"] == [11, 12, 13, 14]
    assert row["status"] == "same"


def test_counts_a_long_statement_once(legacy_checkout: Path) -> None:
    """compare-coverage-against-legacy-counts-a-long-statement-once"""
    target = "targets.compare.long_statement::total"

    result = run_checker("--legacy", str(legacy_checkout), "--target", target)

    row = one_row(result.stdout)
    # the statement spans lines 5 to 7; v2 reports all three, legacy only the first
    for side in ("v2", "legacy"):
        assert 5 in row[side]["covered"], row
        assert not {6, 7} & set(row[side]["covered"]), row
    assert row["status"] == "same"


def test_reads_under_the_decorator(legacy_checkout: Path) -> None:
    """compare-coverage-against-legacy-reads-under-the-decorator"""
    target = "targets.compare.decorated::classify"

    result = run_checker("--legacy", str(legacy_checkout), "--target", target)

    row = one_row(result.stdout)
    assert row["file"] == str(COMPARE / "decorated.py")
    # the body of the wrapped function; the decorator line and the def line are not in it
    assert row["own_lines"] == [8, 9, 10]
    assert row["v2"]["covered"] == row["legacy"]["covered"] == [8, 9, 10]
    assert row["v2"]["file"] == row["legacy"]["file"] == str(COMPARE / "decorated.py")


def test_shows_how_each_side_stopped(legacy_checkout: Path) -> None:
    """compare-coverage-against-legacy-shows-how-each-side-stopped"""
    target = "targets.trace.never_returns::spin"

    result = run_checker("--legacy", str(legacy_checkout), "--target", target, "--budget", "2")

    row = one_row(result.stdout)
    # each side in its own words: legacy's seed times out, and a loop with no fork leaves it
    # nothing to flip, which it calls exhausted
    assert row["v2"]["stopped"] == "budget spent"
    assert row["legacy"]["stopped"] == "exhausted"
    assert row["v2"]["inputs"] >= 1
    assert row["legacy"]["inputs"] >= 1
    assert row["status"] in ("same", "differs")
    assert {2, 3, 4} <= set(row["v2"]["covered"])
    assert {2, 3, 4} <= set(row["legacy"]["covered"])
    (line,) = table_rows(result.stderr, target)
    assert "budget spent" in line
    assert "exhausted" in line


def test_compares_a_target_that_raises(legacy_checkout: Path) -> None:
    """compare-coverage-against-legacy-compares-a-target-that-raises"""
    target = "targets.trace.raises::explode"

    result = run_checker("--legacy", str(legacy_checkout), "--target", target)

    row = one_row(result.stdout)
    assert row["status"] in ("same", "differs")
    # line 2 runs before the raise on line 3
    assert {2, 3} <= set(row["v2"]["covered"])
    assert {2, 3} <= set(row["legacy"]["covered"])

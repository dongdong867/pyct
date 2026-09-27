"""The puts-the-target-back-in-the-gate criterion the checker measures: the finite fork over
`x // 2` in targets.strs.float_position flips within the per-merge limits, so v2 covers the
line past it as legacy does.

The test runs the checker as a person does, against a real checkout of main built once per
session, at the per-merge limits and against the per-merge accepted file, so a v2 that misses
the line again fails it as a changed row.
"""

from pathlib import Path

import pytest

from tests.compare_coverage.acceptance.checker import REPO_ROOT, rows, run_checker

pytestmark = [pytest.mark.legacy, pytest.mark.timeout(180)]

ACCEPTED = REPO_ROOT / "tools" / "compare_coverage" / "accepted-per-merge.jsonl"
FLOAT_POSITION = "targets.strs.float_position::cut"


def test_matches_legacy_on_float_position(legacy_checkout: Path) -> None:
    """solve-a-finite-floor-division-fast-puts-the-target-back-in-the-gate"""
    result = run_checker(
        "--legacy",
        str(legacy_checkout),
        "--target",
        FLOAT_POSITION,
        "--budget",
        "5",
        "--accepted",
        str(ACCEPTED),
    )

    found = rows(result.stdout, result.stderr)
    assert [(row["target"], row["status"]) for row in found] == [(FLOAT_POSITION, "same")], (
        result.stderr
    )
    assert result.returncode == 0, result.stderr

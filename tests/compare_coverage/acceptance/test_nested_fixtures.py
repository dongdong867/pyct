"""The run-with-nested-arguments criterion the checker measures: legacy's own fixtures of
values inside a dict and a list, covered as legacy covers them.

The test runs the checker as a person does, against a real checkout of main built once per
session, at the per-merge limits and against the per-merge accepted file, so a record left
for either fixture would fail it as a changed row.
"""

from pathlib import Path

import pytest

from tests.compare_coverage.acceptance.checker import REPO_ROOT, rows, run_checker

pytestmark = [pytest.mark.legacy, pytest.mark.timeout(180)]

ACCEPTED = REPO_ROOT / "tools" / "compare_coverage" / "accepted-per-merge.jsonl"
NESTED = (
    "tests.acceptance.fixtures.structured.list_items::classify_pair",
    "tests.acceptance.fixtures.structured.nested_dict::validate_config",
)


def test_matches_legacy_on_its_nested_fixtures(legacy_checkout: Path) -> None:
    """run-with-nested-arguments-matches-legacy-on-its-nested-fixtures"""
    targets = [flag for target in NESTED for flag in ("--target", target)]

    result = run_checker(
        "--legacy", str(legacy_checkout), *targets, "--budget", "5", "--accepted", str(ACCEPTED)
    )

    found = rows(result.stdout, result.stderr)
    assert [(row["target"], row["status"]) for row in found] == [
        (target, "same") for target in NESTED
    ], result.stderr
    assert result.returncode == 0, result.stderr

"""Acceptance tests for the seed-a-plain-optional-in-sweep story.

Every test spawns ``python -P -m pyct sweep ...`` from the repository root, so each fixture
module under ``targets/sweep/`` is named from ``targets``. A test that runs entries needs cvc5
on PATH.
"""

import json

import pytest

from tests.acceptance.harness import REPO_ROOT
from tests.acceptance.sweeping import FIXTURES, row_named, sweep

OPTIONAL = f"{FIXTURES}.optional"


def as_json(value: object) -> str:
    """JSON text, which tells 0 from 0.0 and false where == does not."""
    return json.dumps(value)


# sweep-none-default-class-seeds
def test_lists_a_plain_optional_with_null_then_its_value() -> None:
    result = sweep(OPTIONAL, "--list")

    assert result.returncode == 0, result.stderr
    row = row_named(result.stdout, OPTIONAL, "lang_filter")
    assert row["status"] == "listed"
    expected = [{"url": "", "language": None}, {"url": "", "language": ""}]
    assert as_json(row["seed"]) == as_json(expected)


# sweep-none-default-class-seeds
@pytest.mark.timeout(240)
def test_runs_the_code_past_the_none_check() -> None:
    result = sweep(OPTIONAL, "--budget", "10", timeout=230)

    assert result.returncode == 0, result.stderr
    row = row_named(result.stdout, OPTIONAL, "lang_filter")
    assert row["status"] == "ran", row
    path = REPO_ROOT / "targets" / "sweep" / "optional.py"
    lines = path.read_text().splitlines()
    start = lines.index("def lang_filter(url: str, language: str | None = None) -> bool:")
    none_side = lines.index("        return True", start) + 1
    past_check = lines.index('    if language == "en":', start) + 1
    covered = row["run"]["covered"][str(path)]
    assert none_side in covered and past_check in covered, row

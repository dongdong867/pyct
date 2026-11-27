"""Acceptance tests for the seed-a-method-in-sweep story.

Every test spawns ``python -P -m pyct sweep ...`` from the repository root, so each fixture
module under ``targets/sweep/`` is named from ``targets``. A test that runs entries needs cvc5
on PATH.
"""

import json

import pytest

from tests.acceptance.harness import REPO_ROOT
from tests.acceptance.sweeping import FIXTURES, row_named, sweep

ORDERS = f"{FIXTURES}.orders"

# what sweep seeds targets.sweep.orders.Order with
ORDER = {"id": 0, "items": []}


def as_json(value: object) -> str:
    """JSON text, which tells 0 from 0.0 and false where == does not."""
    return json.dumps(value)


# sweep-class-hint-seed
def test_lists_a_class_hint_with_its_constructor_seed() -> None:
    result = sweep(ORDERS, "--list")

    assert result.returncode == 0, result.stderr
    ship = row_named(result.stdout, ORDERS, "ship")
    assert ship["status"] == "listed"
    assert as_json(ship["seed"]) == as_json({"order": ORDER})


# sweep-optional-class-seed
def test_lists_a_class_beside_none_with_its_constructor_seed() -> None:
    result = sweep(ORDERS, "--list")

    assert result.returncode == 0, result.stderr
    maybe = row_named(result.stdout, ORDERS, "maybe")
    assert maybe["status"] == "listed"
    assert as_json(maybe["seed"]) == as_json({"order": ORDER})


# sweep-class-hint-seed
@pytest.mark.timeout(240)
def test_runs_a_class_hinted_seed_as_that_class() -> None:
    result = sweep(ORDERS, "--budget", "10", timeout=230)

    assert result.returncode == 0, result.stderr
    ship = row_named(result.stdout, ORDERS, "ship")
    assert ship["status"] == "ran", ship
    path = REPO_ROOT / "targets" / "sweep" / "orders.py"
    lines = path.read_text().splitlines()
    big = lines.index('        return "big"') + 1
    assert big in ship["run"]["covered"][str(path)], ship

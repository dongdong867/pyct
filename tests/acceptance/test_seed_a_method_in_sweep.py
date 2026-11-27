"""Acceptance tests for the seed-a-method-in-sweep story.

Every test spawns ``python -P -m pyct sweep ...`` from the repository root, so each fixture
module under ``targets/sweep/`` is named from ``targets``. A test that runs entries needs cvc5
on PATH.
"""

import json

import pytest

from tests.acceptance.harness import REPO_ROOT
from tests.acceptance.sweeping import FIXTURES, names, row_named, rows, sweep

ORDERS = f"{FIXTURES}.orders"
METHODS = f"{FIXTURES}.methods"

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


# sweep-none-default-class-seeds
def test_lists_a_class_beside_none_with_null_then_its_constructor_seed() -> None:
    result = sweep(ORDERS, "--list")

    assert result.returncode == 0, result.stderr
    maybe = row_named(result.stdout, ORDERS, "maybe")
    assert maybe["status"] == "listed"
    assert as_json(maybe["seed"]) == as_json([{"order": None}, {"order": ORDER}])


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


def line_of(text: str) -> int:
    """The number of the line of targets/sweep/orders.py that reads ``text``."""
    lines = (REPO_ROOT / "targets" / "sweep" / "orders.py").read_text().splitlines()
    return lines.index(text) + 1


# sweep-method-entry
def test_lists_each_method_with_a_seed() -> None:
    result = sweep(METHODS, "--list")

    assert result.returncode == 0, result.stderr
    seeds = {
        "Cart.total": {"self": {"owner": ""}, "discount": 0},
        "Cart.rate": {"n": 0},
        "Parser.parse": {"self": {}, "text": ""},
    }
    for name, seed in seeds.items():
        row = row_named(result.stdout, METHODS, name)
        assert row["status"] == "listed", row
        assert as_json(row["seed"]) == as_json(seed)
    empty = row_named(result.stdout, METHODS, "Cart.empty")
    assert (empty["status"], empty["reason"]) == ("skipped", "no parameter to vary")
    expected = ["Cart", "Cart.empty", "Cart.rate", "Cart.total", "Parser.parse", "Special"]
    assert names(result.stdout) == expected


# sweep-method-unbuildable
def test_skips_a_method_whose_object_cannot_be_seeded() -> None:
    result = sweep(ORDERS, "--list")

    assert result.returncode == 0, result.stderr
    run = row_named(result.stdout, ORDERS, "Keyed.run")
    written = "no seed for self: no seed for key: collections.abc.Callable[[int], int]"
    assert (run["status"], run["reason"]) == ("skipped", written)
    name = row_named(result.stdout, ORDERS, "Tag.name")
    assert (name["status"], name["reason"]) == ("skipped", "no parameter to vary")
    reasons = {row.get("reason") for row in rows(result.stdout)}
    assert "sweep gives no seed for a method yet" not in reasons


# sweep-method-entry
@pytest.mark.timeout(240)
def test_runs_each_method_as_its_own_run() -> None:
    result = sweep(ORDERS, "--budget", "10", timeout=230)

    assert result.returncode == 0, result.stderr
    path = str(REPO_ROOT / "targets" / "sweep" / "orders.py")
    total = row_named(result.stdout, ORDERS, "Order.total")
    assert total["status"] == "ran", total
    assert line_of("            return max(self.id - discount, 0)") in total["run"]["covered"][path]
    for name in ("Order.count", "Order.blank", "Customer.owes"):
        row = row_named(result.stdout, ORDERS, name)
        assert row["status"] == "ran", row


# sweep-none-default-class-seeds
def test_lists_a_none_default_class_with_two_seeds() -> None:
    result = sweep(ORDERS, "--list")

    assert result.returncode == 0, result.stderr
    later = row_named(result.stdout, ORDERS, "later")
    assert later["status"] == "listed"
    assert as_json(later["seed"]) == as_json([{"order": None}, {"order": ORDER}])
    ship = row_named(result.stdout, ORDERS, "ship")
    assert as_json(ship["seed"]) == as_json({"order": ORDER})


# sweep-none-default-class-seeds
@pytest.mark.timeout(240)
def test_runs_an_entry_with_two_seeds_as_one_run_from_both() -> None:
    result = sweep(ORDERS, "--budget", "10", timeout=230)

    assert result.returncode == 0, result.stderr
    later = row_named(result.stdout, ORDERS, "later")
    assert later["status"] == "ran", later
    path = str(REPO_ROOT / "targets" / "sweep" / "orders.py")
    lines = (REPO_ROOT / "targets" / "sweep" / "orders.py").read_text().splitlines()
    start = lines.index("def later(order: Order | None = None) -> int:")
    none_side = lines.index("        return 0", start) + 1
    built_side = lines.index("    if order.id > 5:", start) + 1
    covered = later["run"]["covered"][path]
    assert none_side in covered and built_side in covered, later

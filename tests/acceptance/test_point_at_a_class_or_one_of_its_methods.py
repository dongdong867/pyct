"""Acceptance tests for point-at-a-class-or-one-of-its-methods.

Each test spawns ``python -P -m pyct`` through the harness, on the class and the objects of
``targets/classes/cart.py``.
"""

import pytest

from tests.acceptance.harness import run_pyct

MODULE = "targets.classes.cart"


# point-at-a-class-or-one-of-its-methods-reports-a-path-that-names-no-function
@pytest.mark.parametrize("name", ["Cart.totl", "Cart.count", "Cart.size"])
def test_reports_a_path_that_names_no_function(name: str) -> None:
    result = run_pyct(f"{MODULE}::{name}", "--args", '{"owner": "ann"}')

    assert result.stderr.splitlines() == [f"{MODULE} has no function {name}"]
    assert result.stdout == ""
    assert result.returncode == 1


# point-at-a-class-or-one-of-its-methods-refuses-a-malformed-path
@pytest.mark.parametrize("name", ["Cart.", ".total", "Cart..total"])
def test_refuses_a_malformed_path(name: str) -> None:
    spec = f"{MODULE}::{name}"

    result = run_pyct(spec, "--args", '{"owner": "ann"}')

    assert result.stderr.splitlines() == [f"target must be MODULE::FUNCTION, got {spec!r}"]
    assert result.stdout == ""
    assert result.returncode == 2

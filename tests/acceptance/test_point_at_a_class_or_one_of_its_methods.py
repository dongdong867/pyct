"""Acceptance tests for point-at-a-class-or-one-of-its-methods.

Each test spawns ``python -P -m pyct`` through the harness, on the class and the objects of
``targets/classes/cart.py``.
"""

import json

import pytest

from tests.acceptance.harness import input_lines, lines_expressions_and_sides, run_pyct

MODULE = "targets.classes.cart"


# point-at-a-class-or-one-of-its-methods-runs-other-kinds-of-method, but Outer.Inner.check, which
# builds self
@pytest.mark.parametrize(
    ("name", "seed"),
    [
        pytest.param("Cart.from_text", {"text": "a"}, id="a-classmethod"),
        pytest.param("Cart.rate", {"x": 0}, id="a-staticmethod"),
        pytest.param("registry.lookup", {"key": "a"}, id="a-method-of-a-module-level-object"),
        pytest.param("handler", {"x": 0}, id="a-callable-object"),
    ],
)
def test_runs_other_kinds_of_method(name: str, seed: dict[str, object]) -> None:
    result = run_pyct(f"{MODULE}::{name}", "--args", json.dumps(seed))

    assert result.returncode == 0, result.stderr
    first, *solved = input_lines(result.stdout)
    [(line, expression, taken)] = lines_expressions_and_sides(first)
    assert first["args"] == seed
    assert taken is False
    other_side = [
        answer
        for answer in solved
        if (line, expression, True) in lines_expressions_and_sides(answer)
    ]
    assert other_side, result.stdout
    assert all(answer["failure"] is None for answer in other_side), result.stdout


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

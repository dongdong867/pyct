"""Acceptance tests for convert-floats-and-read-them-with-math: `math` on a tracked number.

Each test spawns ``python -P -m pyct`` through the harness. pyct substitutes a call of a `math`
function, written `math.sqrt(x)` or `sqrt(x)`, in every module of the target's top-level
package as Python imports it, so only a run through the command line proves it.
"""

import pytest

from tests.acceptance.harness import REPO_ROOT, first_line, input_lines, run_pyct
from tests.acceptance.test_bools import sides
from tests.acceptance.test_floats import expressions, failure_of, real, taken
from tests.acceptance.test_ints import argument, forks_of
from tests.acceptance.test_substitute_conversions import downgrade_names, no_line_lists

FLOATS = REPO_ROOT / "targets" / "floats"
READS = "targets.floats.math_reads::read"
OF_INT = "targets.floats.math_of_int"
UNTAUGHT = "targets.floats.math_untaught::lose"
SQUARE_ROOT = "targets.floats.square_root::f"
SQUARE_ROOT_FILE = str(FLOATS / "square_root.py")

# the fork `math.sqrt` records before it runs, taken true when it does not raise
NOT_NEGATIVE = ["not", ["<", "x", 0.0]]
# each compare `read` makes, one per call, in the order it makes them
COMPARES: list[object] = [
    [">", ["sqrt", "x"], 2.0],
    [">", ["fabs", "x"], 1.0],
    ["<", ["copysign", 1.0, "x"], 0.0],
    ["isnan", "x"],
    ["isinf", "x"],
    ["isfinite", "x"],
    ["isclose", "x", 0.1, 1e-09, 0.0],
]


# follow-builtins-and-conversions-follows-math-on-a-float
@pytest.mark.timeout(90)
def test_follows_math_on_a_float() -> None:
    # cvc5 1.3.4 takes a second or more on each path through `sqrt`, and every path after the
    # first fork goes through it: every side is taken in about 15 s, and an unsat after that
    # can take as long again, so the budget ends the run
    result = run_pyct(READS, '{"x": 0.1}', "--budget", "40", timeout=60)

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    seed = inputs[0]
    assert expressions(seed) == [NOT_NEGATIVE, *COMPARES]
    assert taken(seed) == [True, False, False, False, False, False, True, True]
    assert seed["downgrades"] == []
    for compare in COMPARES:
        assert sides(inputs, compare) == {True, False}, compare


# follow-builtins-and-conversions-follows-math-on-a-tracked-int
def test_follows_math_on_a_tracked_int() -> None:
    result = run_pyct(f"{OF_INT}::root", '{"n": 1}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    compare = [">", ["sqrt", "n"], 3.0]
    assert expressions(inputs[0]) == [["not", ["<", "n", 0.0]], compare]
    # the line that takes the compare's true side, its `n` a JSON int
    solved = [line for line in inputs[1:] if (compare, True) in _forks(line)]
    assert solved and all(argument(line, "n") > 9 for line in solved)
    assert no_line_lists(inputs, "__float__")


def test_follows_math_imported_by_name_on_a_tracked_int() -> None:
    result = run_pyct(f"{OF_INT}::bare_root", '{"n": 1}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    assert sides(inputs, [">", ["sqrt", "n"], 3.0]) == {True, False}
    assert no_line_lists(inputs, "__float__")


# follow-builtins-and-conversions-downgrades-an-untaught-math-function
def test_downgrades_an_untaught_math_function() -> None:
    result = run_pyct(UNTAUGHT, '{"x": 1.0, "n": 4}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert downgrade_names(seed) == [("exp", 1), ("log", 1), ("gcd", 1)]
    assert expressions(seed) == [[">", "x", 0.0]]


# follow-builtins-and-conversions-finds-the-negative-square-root
def test_finds_the_negative_square_root() -> None:
    result = run_pyct(SQUARE_ROOT, '{"x": 4.0}')

    assert result.returncode == 0, result.stderr
    seed, solved = input_lines(result.stdout)[:2]
    fork = {"file": SQUARE_ROOT_FILE, "line": 5, "expression": NOT_NEGATIVE}
    assert [_at(entry) for entry in forks_of(seed)] == [{**fork, "taken": True}]
    assert real(solved, "x") < 0.0
    assert [_at(entry) for entry in forks_of(solved)] == [{**fork, "taken": False}]
    assert failure_of(solved) == ("target_raised", "ValueError")


def _forks(line: dict[str, object]) -> list[tuple[object, object]]:
    return [(fork["expression"], fork["taken"]) for fork in forks_of(line)]


def _at(fork: dict[str, object]) -> dict[str, object]:
    """A fork without its column, which the criterion leaves open."""
    return {key: value for key, value in fork.items() if key != "col"}

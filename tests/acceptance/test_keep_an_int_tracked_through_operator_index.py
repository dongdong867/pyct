"""Acceptance tests for the `index` part of close-four-small-v1-gaps: `operator.index` on a
tracked int keeps it tracked.

Each test spawns ``python -P -m pyct`` through the harness: the call is followed only if the
fork on its answer reaches the solver and the solver's answer, run by plain Python, takes the
other side.
"""

from collections.abc import Callable

import pytest

from targets.ints import operator_index
from tests.acceptance.harness import REPO_ROOT, argument, input_lines, run_pyct
from tests.acceptance.test_fork_on_a_split_s_count_before_it_unpacks import (
    line_of as line_in,
)
from tests.acceptance.test_fork_on_a_split_s_count_before_it_unpacks import raised_by_python
from tests.acceptance.test_lists import (
    downgrade_names,
    failure_detail,
    fork_line,
    listed,
    solved,
)

INDEX = "targets.ints.operator_index"
INDEX_FILE = str(REPO_ROOT / "targets" / "ints" / "operator_index.py")
REBOUND = "targets.ints.rebound_index"


def line_of(text: str, function: str) -> int:
    return line_in(text, INDEX_FILE, after=f"def {function}(")


def covered_by(line: dict[str, object], number: int) -> bool:
    covered = line["covered"]
    assert isinstance(covered, dict), line
    return number in covered.get(INDEX_FILE, [])


# close-four-small-v1-gaps-index-follows-operator-index
def test_follows_operator_index() -> None:
    result = run_pyct(f"{INDEX}::kept", '{"n": 0}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    at = line_of("if k > 10:", "kept")
    assert listed(lines[0]) == [(at, [">", "n", 10], False)]
    assert lines[0]["downgrades"] == []
    assert fork_line(result.stderr, INDEX_FILE, at, "n > 10", False)
    one = line_of("return 1", "kept")
    assert any(argument(line, "n") > 10 and covered_by(line, one) for line in solved(lines))


# close-four-small-v1-gaps-index-follows-a-function-imported-under-another-name
def test_follows_a_function_imported_under_another_name() -> None:
    result = run_pyct(f"{INDEX}::checked", '{"year": 0}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    at = line_of("if not 1 <= year <= 9999:", "checked")
    assert listed(lines[0]) == [(at, [">=", "year", 1], False)]
    inside = [line for line in solved(lines) if 1 <= argument(line, "year") <= 9999]
    # the input inside the range compares the year with both ends, each a fork
    assert inside and listed(inside[0]) == [
        (at, [">=", "year", 1], True),
        (at, ["<=", "year", 9999], True),
    ]
    assert failure_detail(lines[0]) == raised_by_python(lambda: operator_index.checked(0))


# close-four-small-v1-gaps-index-follows-each-spelling
@pytest.mark.parametrize(
    ("function", "fork"),
    [
        ("through_an_alias", ["==", "n", 7]),
        ("of_a_bool", ["==", ["int", [">", "n", 3]], 1]),
    ],
)
def test_follows_each_spelling(function: str, fork: list[object]) -> None:
    result = run_pyct(f"{INDEX}::{function}", '{"n": 0}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert listed(lines[0])[-1][1:] == (fork, False)
    one = line_of("return 1", function)
    assert any(covered_by(line, one) for line in solved(lines)), lines


# close-four-small-v1-gaps-index-leaves-a-name-bound-otherwise-as-written
def test_leaves_a_name_bound_otherwise_as_written() -> None:
    result = run_pyct(f"{REBOUND}::kept", '{"n": 0}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert listed(lines[0]) == []
    assert lines[0]["downgrades"] == []


# close-four-small-v1-gaps-index-leaves-plain-values-as-python
def test_leaves_plain_values_as_python() -> None:
    result = run_pyct(f"{INDEX}::plain", "{}")

    assert result.returncode == 0, result.stderr
    (line,) = input_lines(result.stdout)
    assert line["failure"] is None
    assert listed(line) == [] and line["downgrades"] == []


# close-four-small-v1-gaps-index-raises-python-s-error
@pytest.mark.parametrize(
    ("function", "seed", "call"),
    [
        ("of_a_str", '{"s": "x"}', lambda: operator_index.of_a_str("x")),
        ("with_a_keyword", '{"n": 1}', lambda: operator_index.with_a_keyword(1)),
    ],
)
def test_raises_python_s_error(function: str, seed: str, call: Callable[[], object]) -> None:
    result = run_pyct(f"{INDEX}::{function}", seed)

    assert result.returncode == 0, result.stderr
    line = input_lines(result.stdout)[0]
    assert failure_detail(line) == raised_by_python(call)
    assert downgrade_names(line) == []

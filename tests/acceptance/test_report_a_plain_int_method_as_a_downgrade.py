"""Acceptance tests for the report-a-plain-int-method-as-a-downgrade story.

Each test spawns ``python -P -m pyct`` through the harness: whether a plain method or an
attribute of a tracked number keeps the condition, reads a constant, or names what it lost
shows only on a real run's lines, and a classmethod reached through a tracked value crashed
the target before this story.
"""

import pytest

from tests.acceptance.harness import (
    REPO_ROOT,
    argument,
    first_line,
    forks_of,
    input_lines,
    one_line,
    run_pyct,
    summary_line,
)
from tests.acceptance.test_pass_keywords_through_a_downgrade import covered_in

PLAIN_METHODS = "targets.ints.plain_methods"
PLAIN_METHODS_FILE = str(REPO_ROOT / "targets" / "ints" / "plain_methods.py")
FLOAT_METHODS = "targets.floats.plain_methods::keep_and_lose"
# the line under each of read's three checks, and the `return "built"` of build
UNDER_EACH_CONSTANT = [26, 28, 30]
BUILT = 46


def downgrades_of(line: dict[str, object]) -> list[tuple[object, object]]:
    """Each downgrade on a printed line as its name and count, in the order the line lists them."""
    downgrades = line["downgrades"]
    assert isinstance(downgrades, list), line
    return [(entry["name"], entry["count"]) for entry in downgrades]


def expressions(line: dict[str, object]) -> list[object]:
    """The expression of each fork on a printed line, in order."""
    return [fork["expression"] for fork in forks_of(line)]


def flipped(lines: list[dict[str, object]]) -> list[object]:
    """Every expression some input took true, so the solver reached its other side."""
    return [fork["expression"] for line in lines for fork in forks_of(line) if fork["taken"]]


# report-a-plain-int-method-as-a-downgrade-names-the-method
def test_names_the_method() -> None:
    result = run_pyct(f"{PLAIN_METHODS}::lose", '{"x": 3}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert downgrades_of(seed) == [("bit_length", 1), ("bit_count", 1), ("to_bytes", 1)]
    assert seed["forks"] == []


# report-a-plain-int-method-as-a-downgrade-keeps-the-value-through-an-identity
def test_keeps_the_value_through_an_identity() -> None:
    result = run_pyct(f"{PLAIN_METHODS}::keep", '{"x": 0}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    # each hands back the tracked value itself, as `+x` does, so no node is added
    forks = [[">", "x", 5], [">", "x", 6], [">", "x", 7], [">", "x", 8]]
    assert expressions(lines[0]) == forks
    assert all(fork in flipped(lines) for fork in forks)
    assert all(line["downgrades"] == [] for line in lines)


# report-a-plain-int-method-as-a-downgrade-reads-a-constant-plainly
def test_reads_a_constant_plainly() -> None:
    result = run_pyct(f"{PLAIN_METHODS}::read", '{"x": 3}')

    assert result.returncode == 0, result.stderr
    seed = one_line(result.stdout)
    assert seed["forks"] == []
    assert seed["downgrades"] == []
    assert set(UNDER_EACH_CONSTANT) <= set(covered_in(seed, PLAIN_METHODS_FILE))
    assert summary_line(result.stdout)["stopped"] == "no fork to flip"


# report-a-plain-int-method-as-a-downgrade-reads-a-tracked-bool-as-its-int
def test_reads_a_tracked_bool_as_its_int() -> None:
    result = run_pyct(f"{PLAIN_METHODS}::as_its_int", '{"x": 0}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    seed = lines[0]
    assert [(fork["expression"], fork["taken"]) for fork in forks_of(seed)] == [
        (["==", [">", "x", 0], 1], False)
    ]
    assert downgrades_of(seed) == [("bit_length", 1)]
    assert any(argument(line, "x") > 0 for line in lines if line["source"] == "solver")


# report-a-plain-int-method-as-a-downgrade-treats-a-float-the-same-way
def test_treats_a_float_the_same_way() -> None:
    result = run_pyct(FLOAT_METHODS, '{"f": 0.5}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    forks = [[">", "f", 2.5], ["<", "f", -1.5]]
    assert expressions(lines[0]) == forks
    assert all(fork in flipped(lines) for fork in forks)
    # `f.imag` is float's own 0.0 and records nothing
    assert downgrades_of(lines[0]) == [("as_integer_ratio", 1), ("hex", 1)]


# report-a-plain-int-method-as-a-downgrade-builds-from-a-classmethod-through-a-tracked-value
def test_builds_from_a_classmethod_through_a_tracked_value() -> None:
    result = run_pyct(f"{PLAIN_METHODS}::build", '{"x": 3, "f": 0.5}')

    assert result.returncode == 0, result.stderr
    seed = one_line(result.stdout)
    assert seed["failure"] is None
    assert seed["forks"] == []
    assert seed["downgrades"] == []
    assert BUILT in covered_in(seed, PLAIN_METHODS_FILE)


# report-a-plain-int-method-as-a-downgrade-raises-what-python-raises
def test_raises_what_python_raises() -> None:
    result = run_pyct(f"{PLAIN_METHODS}::overflow", '{"x": 300}')

    assert result.returncode == 0, result.stderr
    seed = one_line(result.stdout)
    with pytest.raises(OverflowError) as plain:
        (300).to_bytes(1, "big")
    assert seed["failure"] == {"kind": "target_raised", "detail": f"OverflowError: {plain.value}"}
    assert seed["downgrades"] == []

"""Acceptance tests for the follow-floats-that-meet-ints child of the follow-floats story.

A tracked int meets a float as Python's numbers do: mixing them, true division, floor division
and modulo, rounding a float to a tracked int, and the forks each raising operation records.
Each test spawns ``python -P -m pyct`` through the harness, as the other float tests do.
"""

import math

from tests.acceptance.harness import (
    REPO_ROOT,
    first_line,
    forks_of,
    input_lines,
    run_pyct,
    summary_line,
    two_lines,
)
from tests.acceptance.test_floats import expressions, failure_of, reached, real, taken

FLOATS = REPO_ROOT / "targets" / "floats"
BODY_MASS = "targets.floats.body_mass::classify"
MIXED = "targets.floats.mixed::mix"
FLOOR_DIVISION = "targets.floats.floor_division::split"
ROUNDING = "targets.floats.rounding::round_off"
HALF_TO_EVEN = "targets.floats.half_to_even::tie"
ABOVE = "targets.floats.above::rate"
TENTH = "targets.floats.tenth::hit"
LARGE_INT = "targets.floats.large_int::near"
SLOW_MODULO = "targets.floats.slow_modulo::rest"
DIVIDE_INTS = "targets.floats.divide_ints::f"
DIVIDE_ONE = "targets.floats.divide_one::f"
FLOOR_DIVIDE = "targets.floats.floor_divide::f"
CANNOT_ROUND = "targets.floats.cannot_round::f"
DIVIDE_BY_BOOLS = "targets.floats.divide_by_bools::ratio"


def whole(line: dict[str, object], name: str) -> int:
    """One int argument off a printed line: a JSON int, never a float that holds a whole number."""
    args = line["args"]
    assert isinstance(args, dict), line
    value = args[name]
    assert type(value) is int, line
    return value


def sides_by_line(lines: list[dict[str, object]], head: str) -> dict[object, set[object]]:
    """The sides each line's forks of one head took, over every input line."""
    sides: dict[object, set[object]] = {}
    for line in lines:
        for fork in forks_of(line):
            expression = fork["expression"]
            if isinstance(expression, list) and expression[0] == head:
                sides.setdefault(fork["line"], set()).add(fork["taken"])
    return sides


def misses(stderr: str) -> list[str]:
    """The stderr lines that report a fork the solver could not flip."""
    return [line for line in stderr.splitlines() if line.startswith("missed ")]


# follow-floats-follows-int-true-division
def test_follows_int_true_division() -> None:
    result = run_pyct(BODY_MASS, '{"h": 170, "w": 60}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    height = ["/", "h", 100]
    compare = [">=", ["/", "w", ["*", height, height]], 25.0]
    assert compare in expressions(inputs[0])
    over = [line for line in inputs[1:] if compare in expressions(line) and taken(line)[-1]]
    assert over, result.stdout
    assert all(type(whole(line, name)) is int for line in inputs for name in ("h", "w"))
    assert all(line["downgrades"] == [] for line in inputs)


# follow-floats-follows-int-true-division
def test_follows_int_true_division_by_a_bool() -> None:
    result = run_pyct(DIVIDE_BY_BOOLS, '{"n": 1, "m": 5}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    # a bool divides as the int 1 or 0 it is, and a tracked one forks on its own condition
    assert expressions(inputs[0]) == [
        [">", ["/", "n", True], 2.5],
        [">", "m", 3],
        [">", ["/", "n", [">", "m", 3]], 2.5],
    ]
    both = {True, False}
    assert sides_by_line(inputs, ">") == {3: both, 5: both}
    assert summary_line(result.stdout)["stopped"] == "no fork to flip"
    assert reached(inputs)


# follow-floats-mixes-ints-and-floats
def test_mixes_ints_and_floats() -> None:
    result = run_pyct(MIXED, '{"n": 0, "x": 10.0}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    assert expressions(inputs[0]) == [[">", ["+", "n", 0.5], "x"], ["<", "n", 2.5]]
    assert sides_by_line(inputs, ">") == {3: {True, False}}
    assert sides_by_line(inputs, "<") == {5: {True, False}}
    assert all(type(whole(line, "n")) is int for line in inputs)
    assert reached(inputs)


# follow-floats-follows-floor-division-and-modulo
def test_follows_floor_division_and_modulo() -> None:
    result = run_pyct(FLOOR_DIVISION, '{"x": 0.0, "y": 1.0}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    assert ["==", ["//", "x", "y"], 4.0] in expressions(inputs[0])
    assert sides_by_line(inputs, "==") == {line: {True, False} for line in (3, 5, 7, 10)}
    # each solver input takes the side it aimed for, so Python agrees with every flip
    assert reached(inputs)


# follow-floats-rounds-to-a-tracked-int
def test_rounds_to_a_tracked_int() -> None:
    result = run_pyct(ROUNDING, '{"x": 0.5, "n": 0}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    compares = [
        part for part in expressions(inputs[0]) if isinstance(part, list) and part[0] != "isfinite"
    ]
    assert compares[0] == ["==", ["floor", "x"], 3]
    assert compares[-1] == ["<", ["floor", "x"], "n"]
    both = {True, False}
    assert sides_by_line(inputs, "==") == {6: both, 8: both, 10: both, 12: both}
    assert sides_by_line(inputs, "<") == {14: both}


# follow-floats-rounds-half-to-even
def test_rounds_half_to_even() -> None:
    result = run_pyct(HALF_TO_EVEN, '{"x": 3.0}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    even = [line for line in inputs if taken(line) == [True, True, True]]
    assert [real(line, "x") for line in even] == [2.5], result.stdout
    assert expressions(even[0])[-1] == ["==", ["round", "x"], 2]


# follow-floats-reads-the-type-from-the-seed
def test_reads_the_type_from_the_seed() -> None:
    as_int = run_pyct(ABOVE, '{"x": 2}')
    as_float = run_pyct(ABOVE, '{"x": 2.0}')

    assert as_int.returncode == 0, as_int.stderr
    assert as_float.returncode == 0, as_float.stderr
    _, int_solved = two_lines(as_int.stdout)
    _, float_solved = two_lines(as_float.stdout)
    assert whole(int_solved, "x") > 2.5
    assert real(float_solved, "x") > 2.5


# follow-floats-finds-no-int-where-python-has-none
def test_finds_no_int_where_python_has_none() -> None:
    result = run_pyct(TENTH, '{"n": 0}')

    assert result.returncode == 0, result.stderr
    assert misses(result.stderr) == [f"missed {FLOATS / 'tenth.py'}:2:7 unsat"]
    lines = result.stdout.splitlines()
    assert len(lines) == 2
    assert "stopped" not in first_line(result.stdout)
    assert summary_line(result.stdout)["inputs"] == 1


# follow-floats-keeps-a-large-int-approximation-honest
def test_keeps_a_large_int_approximation_honest() -> None:
    result = run_pyct(LARGE_INT, '{"n": 0}')

    assert result.returncode == 0, result.stderr
    _, solved = two_lines(result.stdout)
    exact = whole(solved, "n") == 9007199254740996 and solved["mismatch_at"] is None
    assert exact or solved["mismatch_at"] == 0


# follow-floats-reports-a-slow-encoding-as-a-miss
def test_reports_a_slow_encoding_as_a_miss() -> None:
    result = run_pyct(SLOW_MODULO, "--solver-timeout", "0.001", '{"x": 0.0, "y": 1.0}')

    assert result.returncode == 0, result.stderr
    # the zero fork of `x % y` sits at the same place as the compare, and misses as well
    site = f"missed {FLOATS / 'slow_modulo.py'}:2:7 "
    missed = [line.removeprefix(site) for line in misses(result.stderr)]
    assert missed
    assert all(why in ("timeout", "unknown") for why in missed)
    inputs = input_lines(result.stdout)
    remainder = ["==", ["%", "x", "y"], 1.0]
    assert all(
        not fork["taken"]
        for line in inputs
        for fork in forks_of(line)
        if fork["expression"] == remainder
    )


# follow-floats-finds-the-division-by-zero-between-ints
def test_finds_the_division_by_zero_between_ints() -> None:
    result = run_pyct(DIVIDE_INTS, '{"n": 7, "m": 2}')

    assert result.returncode == 0, result.stderr
    seed, solved = two_lines(result.stdout)
    fork = {"file": str(FLOATS / "divide_ints.py"), "line": 2, "col": 11}
    assert forks_of(seed) == [{**fork, "taken": True, "expression": ["!=", "m", 0]}]
    assert seed["downgrades"] == []
    assert whole(solved, "m") == 0
    assert failure_of(solved) == ("target_raised", "ZeroDivisionError")


# follow-floats-finds-the-zero-float-divisor-under-an-int
def test_finds_the_zero_float_divisor_under_an_int() -> None:
    result = run_pyct(DIVIDE_ONE, '{"x": 2.0}')

    assert result.returncode == 0, result.stderr
    seed, solved = two_lines(result.stdout)
    fork: dict[str, object] = {"file": str(FLOATS / "divide_one.py"), "line": 2, "col": 11}
    fork["expression"] = ["!=", "x", 0.0]
    assert forks_of(seed) == [{**fork, "taken": True}]
    assert seed["downgrades"] == []
    assert real(solved, "x") == 0.0
    assert forks_of(solved) == [{**fork, "taken": False}]
    assert failure_of(solved) == ("target_raised", "ZeroDivisionError")


# follow-floats-finds-the-zero-divisor-of-a-floor-division
def test_finds_the_zero_divisor_of_a_floor_division() -> None:
    result = run_pyct(FLOOR_DIVIDE, '{"x": 7.0, "y": 2.0}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    zero = ["!=", "y", 0.0]
    assert [(fork["line"], fork["expression"], fork["taken"]) for fork in forks_of(inputs[0])] == [
        (2, zero, True),
        (2, zero, True),
    ]
    raised = [line for line in inputs[1:] if real(line, "y") == 0.0]
    assert raised, result.stdout
    assert all(failure_of(line) == ("target_raised", "ZeroDivisionError") for line in raised)


# follow-floats-finds-the-value-that-cannot-round
def test_finds_the_value_that_cannot_round() -> None:
    result = run_pyct(CANNOT_ROUND, '{"x": 2.5}')

    assert result.returncode == 0, result.stderr
    seed, solved = two_lines(result.stdout)
    fork: dict[str, object] = {"file": str(FLOATS / "cannot_round.py"), "line": 5, "col": 11}
    fork["expression"] = ["isfinite", "x"]
    assert forks_of(seed) == [{**fork, "taken": True}]
    assert not math.isfinite(real(solved, "x"))
    assert forks_of(solved) == [{**fork, "taken": False}]
    kind, name = failure_of(solved)
    assert (kind, name in ("ValueError", "OverflowError")) == ("target_raised", True)

"""Acceptance tests for the follow-float-compares-and-arithmetic child of the follow-floats story.

Each test spawns ``python -P -m pyct`` through the harness, as the int and string tests do: an
operation on a float is followed only if the fork it built reaches the solver and the solver's
answer runs, so only a real run through the command line proves it.
"""

import math

import pytest

from tests.acceptance.harness import (
    REPO_ROOT,
    downgrade,
    first_line,
    input_lines,
    one_line,
    run_pyct,
    summary_line,
    two_lines,
)
from tests.acceptance.test_strs import covered_of, forks_of

FLOATS = REPO_ROOT / "targets" / "floats"
ABOVE = "targets.floats.above::rate"
ABOVE_FILE = str(FLOATS / "above.py")
SIX_COMPARES = "targets.floats.six_compares::count"
# the line of each compare in ``count``, `2.5 < x` last
COMPARE_LINES = [3, 5, 7, 9, 11, 13, 15]
TRUTH_TEST = "targets.floats.truth_test::tell"
ARITHMETIC = "targets.floats.arithmetic::count"
# each fork ``count`` takes, as the target spells it: a reflected subtraction keeps its order,
# and a unary minus is `-` on one operand
ARITHMETIC_FORKS: list[object] = [
    [">", ["-", ["*", ["+", "x", 1.5], 2.0], 3.0], 10.0],
    [">", ["abs", "x"], 5.0],
    ["<", ["-", "x"], -3.0],
    [">", ["-", 10.0, "x"], "y"],
]
TRUE_DIVISION = "targets.floats.true_division::ratio"
IS_INTEGER = "targets.floats.is_integer::whole"
LITERALS = "targets.floats.literals::count"
LITERALS_FILE = str(FLOATS / "literals.py")
ABOVE_ZERO = "targets.floats.above_zero::sign"
BELOW_TEN = "targets.floats.below_ten::size"
NAN_OR_INFINITY = "targets.floats.nan_or_infinity::kind"
NAN_BESIDE_FINITE = "targets.floats.nan_beside_finite::count"
ROUNDING_EXACT = "targets.floats.rounding_exact::hit"
MINUS_ZERO = "targets.floats.minus_zero::zero"
UNTAUGHT = "targets.floats.untaught::lose"
MIXED_EQUALITY = "targets.floats.mixed_equality::count"
DIVIDE = "targets.floats.divide::f"
DIVIDE_FILE = str(FLOATS / "divide.py")
ORDERED_WITH_STRING = "targets.floats.ordered_with_string::rank"


def real(line: dict[str, object], name: str) -> float:
    """One float argument off a printed line, narrowed so the comparison means something."""
    args = line["args"]
    assert isinstance(args, dict), line
    value = args[name]
    assert isinstance(value, float), line
    return value


def expressions(line: dict[str, object]) -> list[object]:
    """The expression of each fork on a printed line, in order."""
    return [fork["expression"] for fork in forks_of(line)]


def taken(line: dict[str, object]) -> list[object]:
    """The side of each fork on a printed line, in order."""
    return [fork["taken"] for fork in forks_of(line)]


def reached(lines: list[dict[str, object]]) -> bool:
    """Whether every solver input took the path it was solved for, so Python agrees with it."""
    return all(line["mismatch_at"] is None for line in lines if line["source"] == "solver")


def failure_of(line: dict[str, object]) -> tuple[object, str]:
    """The failure's kind, and the name of what the target raised, off a printed line."""
    failure = line["failure"]
    assert isinstance(failure, dict), line
    return failure["kind"], str(failure["detail"]).split(":", 1)[0]


# follow-floats-flips-a-float-compare
def test_flips_a_float_compare() -> None:
    result = run_pyct(ABOVE, '{"x": 0.0}')

    assert result.returncode == 0, result.stderr
    seed, solved = two_lines(result.stdout)
    assert expressions(seed) == [[">", "x", 2.5]]
    assert real(solved, "x") > 2.5
    assert taken(solved) == [True]
    assert covered_of([seed, solved]) == {ABOVE_FILE: [2, 3, 4]}


# follow-floats-follows-every-float-compare
def test_follows_every_float_compare() -> None:
    result = run_pyct(SIX_COMPARES, '{"x": 0.0}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    # Python swaps `2.5 < x` itself and runs `x.__gt__(2.5)`
    assert expressions(inputs[0]) == [
        ["<", "x", 1.0],
        ["<=", "x", 2.0],
        [">", "x", 3.0],
        [">=", "x", 4.0],
        ["==", "x", 5.0],
        ["!=", "x", 6.0],
        [">", "x", 2.5],
    ]
    sides = {(fork["line"], fork["taken"]) for line in inputs for fork in forks_of(line)}
    assert sides == {(line, side) for line in COMPARE_LINES for side in (True, False)}
    assert reached(inputs)
    assert summary_line(result.stdout)["stopped"] == "no fork to flip"


# follow-floats-follows-the-truth-test
def test_follows_the_truth_test() -> None:
    result = run_pyct(TRUTH_TEST, '{"x": 1.5}')

    assert result.returncode == 0, result.stderr
    seed, solved = two_lines(result.stdout)
    # `if not x:` tests x for truth, and zero, 0.0 or -0.0, is the value on the other side
    assert expressions(seed) == [["!=", "x", 0.0]]
    assert seed["downgrades"] == []
    assert real(solved, "x") == 0.0
    assert taken(solved) == [False]


# follow-floats-flips-through-arithmetic
def test_flips_through_arithmetic() -> None:
    result = run_pyct(ARITHMETIC, '{"x": 0.0, "y": 0.0}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    assert expressions(inputs[0]) == ARITHMETIC_FORKS
    # the literals are floats on the line, as the target wrote them
    assert repr(expressions(inputs[0])) == repr(ARITHMETIC_FORKS)
    sides = {
        (repr(fork["expression"]), fork["taken"]) for line in inputs for fork in forks_of(line)
    }
    assert sides == {(repr(fork), side) for fork in ARITHMETIC_FORKS for side in (True, False)}
    assert reached(inputs)
    assert all(line["downgrades"] == [] for line in inputs)


# follow-floats-follows-true-division
def test_follows_true_division() -> None:
    result = run_pyct(TRUE_DIVISION, '{"x": 1.0, "y": 1.0}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    compare = [">", ["/", "x", "y"], 2.5]
    # the zero fork goes in before the division runs, so it comes before the compare
    assert list(zip(expressions(inputs[0]), taken(inputs[0]), strict=True)) == [
        (["!=", "y", 0.0], True),
        (compare, False),
    ]
    solved = [line for line in inputs[1:] if compare in expressions(line)]
    assert any(taken(line) == [True, True] for line in solved), result.stdout
    assert reached(inputs)


# follow-floats-follows-is-integer
def test_follows_is_integer() -> None:
    result = run_pyct(IS_INTEGER, '{"x": 2.5}')

    assert result.returncode == 0, result.stderr
    seed, solved = two_lines(result.stdout)
    assert expressions(seed) == [["is_integer", "x"]]
    assert real(solved, "x").is_integer()
    assert taken(solved) == [True]


# follow-floats-prints-float-literals-as-python-writes-them
def test_prints_float_literals_as_python_writes_them() -> None:
    result = run_pyct(LITERALS, '{"x": 0.5}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert expressions(seed) == [["<", "x", 1e-05], ["!=", "x", 2.0]]
    # the text, not only the parsed value: `2.0` stays a float and `1e-05` keeps its exponent
    line = result.stdout.splitlines()[0]
    assert '"expression": ["<", "x", 1e-05]' in line
    assert '"expression": ["!=", "x", 2.0]' in line
    stderr = result.stderr.splitlines()
    assert f"fork {LITERALS_FILE}:3:7  x < 1e-05  not taken" in stderr
    assert f"fork {LITERALS_FILE}:5:7  x != 2.0  taken" in stderr


# follow-floats-answers-a-finite-float-first
@pytest.mark.parametrize(
    ("target", "seed"), [(ABOVE_ZERO, '{"x": -1.0}'), (BELOW_TEN, '{"x": 5.0}')]
)
def test_answers_a_finite_float_first(target: str, seed: str) -> None:
    result = run_pyct(target, seed)

    assert result.returncode == 0, result.stderr
    seeded, solved = two_lines(result.stdout)
    assert taken(solved) == [not side for side in taken(seeded)]
    assert math.isfinite(real(solved, "x"))
    # cvc5 answers NaN for either flip when every double is allowed from the start
    assert "NaN" not in result.stdout
    assert "Infinity" not in result.stdout


# follow-floats-answers-a-finite-float-first
def test_answers_a_finite_float_beside_one_only_nan_serves() -> None:
    result = run_pyct(NAN_BESIDE_FINITE, '{"x": 1.0, "y": 1.0}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    # the path with x NaN and y flipped below zero: only x needs a NaN, so y stays finite
    below = [
        line for line in inputs if math.isnan(real(line, "x")) and taken(line) == [True, False]
    ]
    assert below, result.stdout
    assert all(math.isfinite(real(line, "y")) for line in below)
    assert reached(inputs)


# follow-floats-answers-nan-or-infinity-only-when-needed
def test_answers_nan_or_infinity_only_when_needed() -> None:
    result = run_pyct(NAN_OR_INFINITY, '{"x": 1.0}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    by_value = {repr(real(line, "x")): line for line in inputs[1:]}
    # NaN is the one double unequal to itself, and infinity the one above the largest finite
    assert taken(by_value["nan"])[0] is True
    assert taken(by_value["inf"]) == [False, True]
    assert reached(inputs)
    assert '"x": NaN' in result.stdout
    assert '"x": Infinity' in result.stdout


# follow-floats-keeps-float-rounding-exact
def test_keeps_float_rounding_exact() -> None:
    result = run_pyct(ROUNDING_EXACT, '{"x": 0.0}')

    assert result.returncode == 0, result.stderr
    _, solved = two_lines(result.stdout)
    # 0.2 is no answer: 0.2 + 0.1 is 0.30000000000000004 in Python, and in the solver
    assert taken(solved) == [True]
    assert solved["mismatch_at"] is None
    assert real(solved, "x") + 0.1 == 0.3


# follow-floats-treats-minus-zero-as-zero
def test_treats_minus_zero_as_zero() -> None:
    result = run_pyct(MINUS_ZERO, '{"y": -0.0}')

    assert result.returncode == 0, result.stderr
    seed, solved = two_lines(result.stdout)
    assert math.copysign(1.0, real(seed, "y")) == -1.0
    assert taken(seed) == [True]
    assert real(solved, "y") != 0.0
    assert taken(solved) == [False]
    assert solved["mismatch_at"] is None


# follow-floats-downgrades-an-untaught-float-operation
def test_downgrades_an_untaught_float_operation() -> None:
    result = run_pyct(UNTAUGHT, '{"x": 1.5}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    # an operator by its dunder, a method by its name; a bool beside a float is float's own.
    # `int(x)` written in the target's package is a tracked int after its finite fork, no
    # longer a downgrade (intercept-builtin-functions-follows-int-of-a-float)
    at = "targets/floats/untaught.py"
    assert seed["downgrades"] == [
        downgrade("__pow__", 1, f"{at}:2:4"),
        downgrade("__round__", 1, f"{at}:4:4"),
        downgrade("hex", 1, f"{at}:5:4"),
        downgrade("__str__", 1, f"{at}:6:4"),
        downgrade("__add__", 1, f"{at}:7:4"),
    ]
    assert expressions(seed) == [["isfinite", "x"], [">", "x", 0.0]]


# follow-floats-treats-a-mixed-equality-as-plain
def test_treats_a_mixed_equality_as_plain() -> None:
    result = run_pyct(MIXED_EQUALITY, '{"x": 1.5}')

    assert result.returncode == 0, result.stderr
    seed = one_line(result.stdout)
    # Python answers a float against a str with a constant, so nothing forks and nothing is lost
    assert seed["forks"] == []
    assert seed["downgrades"] == []


# follow-floats-finds-the-division-by-zero
def test_finds_the_division_by_zero() -> None:
    result = run_pyct(DIVIDE, '{"x": 7.0, "y": 2.0}')

    assert result.returncode == 0, result.stderr
    seed, solved = two_lines(result.stdout)
    fork = {"file": DIVIDE_FILE, "line": 2, "col": 11, "expression": ["!=", "y", 0.0]}
    assert forks_of(seed) == [{**fork, "taken": True}]
    assert real(solved, "y") == 0.0
    assert forks_of(solved) == [{**fork, "taken": False}]
    assert failure_of(solved) == ("target_raised", "ZeroDivisionError")


# follow-floats-reports-an-ordered-compare-with-a-string
def test_reports_an_ordered_compare_with_a_string() -> None:
    result = run_pyct(ORDERED_WITH_STRING, '{"x": 1.5}')

    assert result.returncode == 0, result.stderr
    seed = one_line(result.stdout)
    assert failure_of(seed) == ("target_raised", "TypeError")
    assert summary_line(result.stdout)["stopped"] == "no fork to flip"

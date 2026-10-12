"""Acceptance tests for the follow-integers story.

Each test spawns ``python -P -m pyct`` through the harness, the way the finish-a-run
tests do: an operation is followed only if the fork it built reaches the solver and the
solver's answer runs, so only a real run through the command line proves it.
"""

from subprocess import CompletedProcess

from tests.acceptance.harness import (
    REPO_ROOT,
    argument,
    downgrade,
    forks_of,
    input_lines,
    numbers_of,
    one_line,
    run_pyct,
    summary_line,
    two_lines,
    union_of,
)

SIX_CHECKS = "targets.ints.six_checks::count"
SIX_CHECKS_FILE = str(REPO_ROOT / "targets" / "ints" / "six_checks.py")
# every line of ``count`` but its ``def``, which runs at import rather than under an input
COUNT_LINES = list(range(2, 16))
REFLECTED_CHECK = "targets.ints.reflected_check::rank"
REFLECTED_CHECK_FILE = str(REPO_ROOT / "targets" / "ints" / "reflected_check.py")
TRUTH_TEST = "targets.ints.truth_test::tell"
TRUTH_TEST_FILE = str(REPO_ROOT / "targets" / "ints" / "truth_test.py")
BIT_CHECK = "targets.ints.bit_check::parity"
TRUE_DIVISION = "targets.ints.true_division::halve"
ARITHMETIC_CHECK = "targets.ints.arithmetic_check::grade"
ARITHMETIC_CHECK_FILE = str(REPO_ROOT / "targets" / "ints" / "arithmetic_check.py")
ABS_AND_NEGATION = "targets.ints.abs_and_negation::place"
ABS_AND_NEGATION_FILE = str(REPO_ROOT / "targets" / "ints" / "abs_and_negation.py")
CONSTANT_POWER = "targets.ints.constant_power::root"
CONSTANT_POWER_FILE = str(REPO_ROOT / "targets" / "ints" / "constant_power.py")
TWO_ARGUMENTS = "targets.ints.two_arguments::product"
TWO_ARGUMENTS_FILE = str(REPO_ROOT / "targets" / "ints" / "two_arguments.py")
TAUGHT_ONLY = "targets.ints.taught_only::check"
SYMBOLIC_EXPONENT = "targets.ints.symbolic_exponent::grow"
IDENTITY_CHECK = "targets.ints.identity_check::small"
DIVMOD_CHECK = "targets.ints.divmod_check::split"
NEGATIVE_FLOOR = "targets.ints.negative_floor::band"
NEGATIVE_FLOOR_FILE = str(REPO_ROOT / "targets" / "ints" / "negative_floor.py")
NEGATIVE_MODULO = "targets.ints.negative_modulo::band"
NEGATIVE_MODULO_FILE = str(REPO_ROOT / "targets" / "ints" / "negative_modulo.py")
FLOOR_DIVISION = "targets.ints.floor_division::share"
FLOOR_DIVISION_FILE = str(REPO_ROOT / "targets" / "ints" / "floor_division.py")
REFLECTED_DIVISION = "targets.ints.reflected_division::share"
REFLECTED_DIVISION_FILE = str(REPO_ROOT / "targets" / "ints" / "reflected_division.py")
COUNTED_UP = "targets.ints.counted_up::count_up"


# follow-integers-flips-every-comparison
def test_flips_every_comparison() -> None:
    result = run_pyct(SIX_CHECKS, '{"x": 0}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    # the seed takes one side of each of the six checks; the other side of each is a fork
    # to flip, and the input that flips it runs the line under that check
    assert union_of(inputs) == {SIX_CHECKS_FILE: COUNT_LINES}
    summary = summary_line(result.stdout)
    # nothing is left over: the import ran the ``def`` line no input can run
    assert numbers_of(summary, "uncovered") == {SIX_CHECKS_FILE: []}
    assert summary["stopped"] == "no fork to flip"


# follow-integers-flips-a-reflected-comparison
def test_flips_a_reflected_comparison() -> None:
    result = run_pyct(REFLECTED_CHECK, '{"x": 0}')

    assert result.returncode == 0, result.stderr
    seed, solved = two_lines(result.stdout)
    # Python swaps the operands of `10 < x` itself, so the fork is the one it ran, `x > 10`
    assert seed["forks"] == [
        {
            "file": REFLECTED_CHECK_FILE,
            "line": 2,
            "col": 7,
            "taken": False,
            "expression": [">", "x", 10],
        }
    ]
    assert solved["forks"] == [
        {
            "file": REFLECTED_CHECK_FILE,
            "line": 2,
            "col": 7,
            "taken": True,
            "expression": [">", "x", 10],
        }
    ]
    assert argument(solved, "x") > 10


# follow-integers-flips-a-truth-test
def test_flips_a_truth_test() -> None:
    result = run_pyct(TRUTH_TEST, '{"x": 5}')

    assert result.returncode == 0, result.stderr
    seed, solved = two_lines(result.stdout)
    # `if x:` is a fork on its own, and the only input that takes the other side is zero
    assert seed["forks"] == [
        {
            "file": TRUTH_TEST_FILE,
            "line": 2,
            "col": 7,
            "taken": True,
            "expression": ["!=", "x", 0],
        }
    ]
    assert argument(solved, "x") == 0
    assert union_of([seed, solved]) == {TRUTH_TEST_FILE: [2, 3, 4]}


# follow-integers-keeps-bit-operations-as-downgrades
def test_keeps_bit_operations_as_downgrades() -> None:
    result = run_pyct(BIT_CHECK, '{"x": 1}')

    assert result.returncode == 0, result.stderr
    seed = one_line(result.stdout)
    assert seed["downgrades"] == [downgrade("__and__", 1, "targets/ints/bit_check.py:2:7")]
    # `x & 1` is a plain int, and the truth of a plain int is nothing pyct can flip
    assert seed["forks"] == []
    assert summary_line(result.stdout)["stopped"] == "no fork to flip"


# follow-integers-keeps-true-division-as-a-downgrade, until follow-floats-that-meet-ints taught
# `/` (follow-floats-follows-int-true-division)
def test_follows_true_division_into_a_float() -> None:
    result = run_pyct(TRUE_DIVISION, '{"x": 4}')

    assert result.returncode == 0, result.stderr
    seed, solved = two_lines(result.stdout)
    assert seed["downgrades"] == []
    # `x / 2` is a tracked float, and the compare after it is a fork the solver flips
    assert [fork["expression"] for fork in forks_of(seed)] == [[">", ["/", "x", 2], 1]]
    args = solved["args"]
    assert isinstance(args, dict) and type(args["x"]) is int and args["x"] / 2 <= 1


# follow-integers-flips-through-arithmetic
def test_flips_through_arithmetic() -> None:
    result = run_pyct(ARITHMETIC_CHECK, '{"x": 0}')

    assert result.returncode == 0, result.stderr
    seed, solved = two_lines(result.stdout)
    # the expression is the arithmetic as written, innermost first, with the compare on top
    assert seed["forks"] == [
        {
            "file": ARITHMETIC_CHECK_FILE,
            "line": 2,
            "col": 7,
            "taken": False,
            "expression": [">", ["-", ["*", ["+", "x", 1], 2], 3], 10],
        }
    ]
    assert (argument(solved, "x") + 1) * 2 - 3 > 10
    assert union_of([seed, solved]) == {ARITHMETIC_CHECK_FILE: [2, 3, 4]}


# follow-integers-flips-through-abs-and-negation
def test_flips_through_abs_and_negation() -> None:
    result = run_pyct(ABS_AND_NEGATION, '{"x": 0}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    seed = inputs[0]
    # a builtin is its name, and a unary minus is `-` with one operand
    assert [fork["expression"] for fork in forks_of(seed)] == [
        [">", ["abs", "x"], 5],
        ["<", ["-", "x"], -3],
    ]
    assert [fork["taken"] for fork in forks_of(seed)] == [False, False]
    # each fork gets flipped: some input takes the true side of each
    sides = [tuple(fork["taken"] for fork in forks_of(line)) for line in inputs]
    assert any(taken[0] for taken in sides if taken)
    assert any(len(taken) == 2 and taken[1] for taken in sides)
    assert all(line["downgrades"] == [] for line in inputs)


# follow-integers-flips-a-constant-power
def test_flips_a_constant_power() -> None:
    result = run_pyct(CONSTANT_POWER, '{"x": 0}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    # the inner check is reached once the outer fork is flipped, and prints the power as written
    inner = [fork for line in inputs for fork in forks_of(line) if fork["line"] == 3]
    assert inner, inputs
    assert inner[0]["expression"] == ["==", ["**", "x", 2], 9]
    # only one negative int squares to nine
    assert any(argument(line, "x") == -3 for line in inputs)
    assert union_of(inputs) == {CONSTANT_POWER_FILE: [2, 3, 4, 5, 6]}


# follow-integers-follows-two-arguments-together
def test_follows_two_arguments_together() -> None:
    result = run_pyct(TWO_ARGUMENTS, '{"x": 2, "y": 2}')

    assert result.returncode == 0, result.stderr
    seed, solved = two_lines(result.stdout)
    assert [fork["expression"] for fork in forks_of(seed)] == [["==", ["*", "x", "y"], 12]]
    # the solver may move either argument; what it hands back multiplies to twelve
    assert argument(solved, "x") * argument(solved, "y") == 12
    assert union_of([seed, solved]) == {TWO_ARGUMENTS_FILE: [2, 3, 4]}


# follow-integers-drops-taught-operations-from-the-downgrade-list
def test_drops_taught_operations_from_the_downgrade_list() -> None:
    result = run_pyct(TAUGHT_ONLY, '{"x": 0}')

    assert result.returncode == 0, result.stderr
    seed = input_lines(result.stdout)[0]
    # `+`, `abs` and `==` each keep the condition, so nothing was lost on the way
    assert seed["downgrades"] == []


# follow-integers-keeps-a-symbolic-exponent-as-a-downgrade
def test_keeps_a_symbolic_exponent_as_a_downgrade() -> None:
    result = run_pyct(SYMBOLIC_EXPONENT, '{"x": 1}')

    assert result.returncode == 0, result.stderr
    seed = one_line(result.stdout)
    # cvc5 takes a constant exponent only, so `2 ** x` reaches int's own reflected power
    assert seed["downgrades"] == [downgrade("__rpow__", 1, "targets/ints/symbolic_exponent.py:2:7")]
    assert seed["forks"] == []
    assert summary_line(result.stdout)["stopped"] == "no fork to flip"


# follow-integers-keeps-the-condition-through-identity-operations
def test_keeps_the_condition_through_identity_operations() -> None:
    result = run_pyct(IDENTITY_CHECK, '{"x": 20}')

    assert result.returncode == 0, result.stderr
    seed, solved = two_lines(result.stdout)
    # round and unary plus change nothing about an int, so the expression is the argument itself
    assert [fork["expression"] for fork in forks_of(seed)] == [["<", "x", 10]]
    assert seed["downgrades"] == []
    assert solved["downgrades"] == []
    assert argument(solved, "x") < 10


# follow-integers-flips-divmod
def test_flips_divmod() -> None:
    result = run_pyct(DIVMOD_CHECK, '{"x": 0}')

    assert result.returncode == 0, result.stderr
    seed, solved = two_lines(result.stdout)
    # divmod hands back both halves at once; the check reads the remainder, so that is
    # the half the fork is built on, and the divisor is a constant, so nothing forks on it
    assert [fork["expression"] for fork in forks_of(seed)] == [["==", ["%", "x", 5], 3]]
    assert [fork["taken"] for fork in forks_of(solved)] == [True]


# follow-integers-flips-floor-division-with-a-negative-divisor
def test_flips_floor_division_with_a_negative_divisor() -> None:
    result = run_pyct(NEGATIVE_FLOOR, '{"x": 0}')

    assert result.returncode == 0, result.stderr
    seed, solved = two_lines(result.stdout)
    # Python floors toward minus infinity, so `9 // -2` is -5 while `8 // -2` and `7 // -2`
    # are -4; an encoding that truncated instead would hand back an x that misses the block
    assert [fork["taken"] for fork in forks_of(solved)] == [True]
    assert solved["mismatch_at"] is None
    assert union_of([seed, solved]) == {NEGATIVE_FLOOR_FILE: [2, 3, 4]}


# follow-integers-flips-modulo-with-a-negative-divisor
def test_flips_modulo_with_a_negative_divisor() -> None:
    result = run_pyct(NEGATIVE_MODULO, '{"x": 0}')

    assert result.returncode == 0, result.stderr
    seed, solved = two_lines(result.stdout)
    # Python's modulo takes the divisor's sign, so `2 % -3` is -1; a remainder that came
    # back non-negative would never equal -1 and the flip would miss the block
    assert [fork["taken"] for fork in forks_of(solved)] == [True]
    assert solved["mismatch_at"] is None
    assert union_of([seed, solved]) == {NEGATIVE_MODULO_FILE: [2, 3, 4]}


def assert_the_zero_fork_was_flipped(result: CompletedProcess[str], file: str) -> None:
    """The whole story of a division by a symbolic divisor, which both forms tell alike.

    The seed divides by something that is not zero and records the fork that
    says so; flipping it is asking for the divisor the division cannot take,
    and the input that comes back crashes on it.
    """
    assert result.returncode == 0, result.stderr
    seed, solved = two_lines(result.stdout)
    division = {"file": file, "line": 2, "col": 11}
    assert forks_of(seed) == [{**division, "taken": True, "expression": ["!=", "y", 0]}]
    assert solved["aim"] == {**division, "position": 0}
    assert argument(solved, "y") == 0
    assert forks_of(solved) == [{**division, "taken": False, "expression": ["!=", "y", 0]}]
    # the detail is CPython's own sentence, so only the kind and the name are pyct's to pin
    failure = solved["failure"]
    assert isinstance(failure, dict), solved
    assert failure["kind"] == "target_raised"
    assert str(failure["detail"]).startswith("ZeroDivisionError:")


# follow-integers-finds-the-division-by-zero
def test_finds_the_division_by_zero() -> None:
    result = run_pyct(FLOOR_DIVISION, '{"x": 7, "y": 2}')

    assert_the_zero_fork_was_flipped(result, FLOOR_DIVISION_FILE)


# follow-integers-finds-the-division-by-zero-on-the-reflected-side
def test_finds_the_division_by_zero_on_the_reflected_side() -> None:
    result = run_pyct(REFLECTED_DIVISION, '{"y": 2}')

    # `7 // y` runs int's reflected divide on y, and the fork is the same divisor's
    assert_the_zero_fork_was_flipped(result, REFLECTED_DIVISION_FILE)


# follow-integers-flips-through-arithmetic
def test_flips_through_a_sum_built_over_five_thousand_passes() -> None:
    result = run_pyct(COUNTED_UP, '{"x": 0}')

    # the sum nests five thousand additions deep, far past Python's recursion limit, and the
    # line, the fork line and the solver each walk it
    assert result.returncode == 0, result.stderr
    seed, solved = two_lines(result.stdout)
    assert [fork["taken"] for fork in forks_of(seed)] == [False]
    assert argument(solved, "x") + 5000 > 5010
    assert solved["mismatch_at"] is None
    assert summary_line(result.stdout)["stopped"] == "no fork to flip"

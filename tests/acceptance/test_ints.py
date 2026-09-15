"""Acceptance tests for the follow-integers story.

Each test spawns ``python -P -m pyct`` through the harness, the way the finish-a-run
tests do: an operation is followed only if the fork it built reaches the solver and the
solver's answer runs, so only a real run through the command line proves it.
"""

from tests.acceptance.harness import (
    REPO_ROOT,
    input_lines,
    one_line,
    run_pyct,
    summary_line,
    two_lines,
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


def argument(line: dict[str, object], name: str) -> int:
    """One int argument off a printed line, narrowed so the comparison means something."""
    args = line["args"]
    assert isinstance(args, dict), line
    value = args[name]
    assert isinstance(value, int), line
    return value


def numbers_of(line: dict[str, object], key: str) -> dict[str, list[int]]:
    """One map of line numbers off a printed line, narrowed so a lookup means something."""
    payload = line[key]
    assert isinstance(payload, dict), line
    return {str(file): [int(number) for number in lines] for file, lines in payload.items()}


def union_of(lines: list[dict[str, object]]) -> dict[str, list[int]]:
    """Every input's covered map added up, written the way a printed line writes one."""
    union: dict[str, set[int]] = {}
    for line in lines:
        for file, covered in numbers_of(line, "covered").items():
            union[file] = union.get(file, set()) | set(covered)
    return {file: sorted(covered) for file, covered in union.items()}


# follow-integers-flips-every-comparison
def test_flips_every_comparison() -> None:
    result = run_pyct(SIX_CHECKS, '{"x": 0}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    # the seed takes one side of each of the six checks; the other side of each is a fork
    # to flip, and the input that flips it runs the line under that check
    assert union_of(inputs) == {SIX_CHECKS_FILE: COUNT_LINES}
    summary = summary_line(result.stdout)
    # nothing is left over but the ``def`` line no input can run
    assert numbers_of(summary, "uncovered") == {SIX_CHECKS_FILE: [1]}
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
    assert seed["downgrades"] == [{"name": "__and__", "count": 1}]
    # `x & 1` is a plain int, and the truth of a plain int is nothing pyct can flip
    assert seed["forks"] == []
    assert summary_line(result.stdout)["stopped"] == "no fork to flip"


# follow-integers-keeps-true-division-as-a-downgrade
def test_keeps_true_division_as_a_downgrade() -> None:
    result = run_pyct(TRUE_DIVISION, '{"x": 4}')

    assert result.returncode == 0, result.stderr
    seed = one_line(result.stdout)
    assert seed["downgrades"] == [{"name": "__truediv__", "count": 1}]
    # `x / 2` is a plain float, so the compare after it is Python's own and forks nothing
    assert seed["forks"] == []
    assert summary_line(result.stdout)["stopped"] == "no fork to flip"


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


def forks_of(line: dict[str, object]) -> list[dict[str, object]]:
    """The forks off a printed line, narrowed so a field lookup means something."""
    forks = line["forks"]
    assert isinstance(forks, list), line
    return [dict(fork) for fork in forks]


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

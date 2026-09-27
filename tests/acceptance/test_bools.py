"""Acceptance tests for the follow-booleans-and-chained-compares story.

Each test spawns ``python -P -m pyct`` through the harness, as the follow-integers tests
do: a condition is followed only if the fork it built reaches the solver and the solver's
answer runs, so only a real run through the command line proves it.
"""

from tests.acceptance.harness import (
    REPO_ROOT,
    downgrade,
    first_line,
    input_lines,
    one_line,
    run_pyct,
    summary_line,
)
from tests.acceptance.test_ints import argument, forks_of

AND_OR = "targets.bools.and_or::both"
AND_OR_FILE = str(REPO_ROOT / "targets" / "bools" / "and_or.py")
CHAINED = "targets.bools.chained::band"
CHAINED_FILE = str(REPO_ROOT / "targets" / "bools" / "chained.py")
NOT_AND_TERNARY = "targets.bools.not_and_ternary::pick"
STORED = "targets.bools.stored::later"
STORED_FILE = str(REPO_ROOT / "targets" / "bools" / "stored.py")
COUNTS = "targets.bools.counts::tally"
COMBINES = "targets.bools.combines::combine"
BOOL_LITERAL = "targets.bools.bool_literal::shift"
BOOL_LITERAL_FILE = str(REPO_ROOT / "targets" / "bools" / "bool_literal.py")
MEMBERSHIP = "targets.bools.membership::member"
BUILTIN_TRUTH = "targets.bools.builtin_truth::check"
UNTESTED = "targets.bools.untested::positive"
UNTAUGHT = "targets.bools.untaught::lose"
FAILING_ASSERT = "targets.bools.failing_assert::check"
FALSE_DIVISOR = "targets.bools.false_divisor::share"
COMPARE_WITH_STR = "targets.bools.compare_with_str::mix"


def expressions(line: dict[str, object]) -> list[object]:
    """The expression of each fork on a printed line, in the order the input met them."""
    return [fork["expression"] for fork in forks_of(line)]


def sides(inputs: list[dict[str, object]], expression: object) -> set[object]:
    """Every side any input took at a fork with this expression."""
    return {
        fork["taken"]
        for line in inputs
        for fork in forks_of(line)
        if fork["expression"] == expression
    }


def at(line: dict[str, object], number: int) -> list[object]:
    """The expressions of the forks a printed line lists at one line of the target."""
    return [fork["expression"] for fork in forks_of(line) if fork["line"] == number]


def failure_of(line: dict[str, object]) -> dict[str, object]:
    """The failure off a printed line, narrowed so a field lookup means something."""
    failure = line["failure"]
    assert isinstance(failure, dict), line
    return failure


# follow-booleans-and-chained-compares-follows-and-and-or
def test_follows_and_and_or() -> None:
    result = run_pyct(AND_OR, '{"x": 0, "y": 0}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    # `and` stops at the first false operand, so `y > 0` is never tested; `or` tests both
    assert [(fork["line"], fork["col"], fork["expression"]) for fork in forks_of(inputs[0])] == [
        (2, 7, [">", "x", 0]),
        (4, 7, ["<", "x", -5]),
        (4, 17, ["<", "y", -5]),
    ]
    assert all(fork["taken"] is False for fork in forks_of(inputs[0]))
    for compare in ([">", "x", 0], [">", "y", 0], ["<", "x", -5], ["<", "y", -5]):
        assert sides(inputs, compare) == {True, False}, compare


# follow-booleans-and-chained-compares-follows-a-chained-compare
def test_follows_a_chained_compare() -> None:
    result = run_pyct(CHAINED, '{"x": -1}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    link = {"file": CHAINED_FILE, "line": 2, "col": 7}
    assert forks_of(inputs[0]) == [{**link, "taken": False, "expression": [">=", "x", 0]}]
    # the chain is Python's `and` of its links, both at the column where the chain starts
    assert {**link, "taken": True, "expression": [">=", "x", 0]} in forks_of(inputs[1])
    assert expressions(inputs[1]) == [[">=", "x", 0], ["<", "x", 10]]
    assert [(fork["line"], fork["col"]) for fork in forks_of(inputs[1])] == [(2, 7), (2, 7)]
    assert sides(inputs, ["<", "x", 10]) == {True, False}


# follow-booleans-and-chained-compares-follows-not-and-the-ternary
def test_follows_not_and_the_ternary() -> None:
    result = run_pyct(NOT_AND_TERNARY, '{"x": 0, "y": 0}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    # `not` records the condition it negates, with the side that condition took
    assert [(fork["line"], fork["expression"], fork["taken"]) for fork in forks_of(inputs[0])] == [
        (2, [">", "x", 3], False),
        (4, [">", "y", 3], False),
    ]
    assert True in sides(inputs, [">", "x", 3])
    assert True in sides(inputs, [">", "y", 3])


# follow-booleans-and-chained-compares-keeps-a-stored-condition
def test_keeps_a_stored_condition() -> None:
    result = run_pyct(STORED, '{"x": 0}')

    assert result.returncode == 0, result.stderr
    seed, solved = input_lines(result.stdout)[:2]
    # the compare runs on line 2, but nothing tests it until `if y:` on line 3
    assert forks_of(seed) == [
        {"file": STORED_FILE, "line": 3, "col": 7, "taken": False, "expression": [">", "x", 0]}
    ]
    assert argument(solved, "x") > 0
    assert [fork["taken"] for fork in forks_of(solved)] == [True]


# follow-booleans-and-chained-compares-counts-conditions
def test_counts_conditions() -> None:
    result = run_pyct(COUNTS, '{"x": 0, "y": 0}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    first, second = expressions(inputs[0])
    # a compare's answer is 1 or 0 as a number, as in Python
    assert first == ["==", ["+", [">", "x", 0], [">", "y", 0]], 2]
    assert [">", "x", 5] in _parts(second)
    assert [">", "y", 5] in _parts(second)
    assert sides(inputs, first) == {True, False}
    assert sides(inputs, second) == {True, False}
    assert all(line["downgrades"] == [] for line in inputs)


def _parts(expression: object) -> list[object]:
    """An expression and every part nested in it."""
    if not isinstance(expression, list):
        return [expression]
    return [expression, *(part for operand in expression[1:] for part in _parts(operand))]


# follow-booleans-and-chained-compares-combines-conditions
def test_combines_conditions() -> None:
    result = run_pyct(COMBINES, '{"x": 1, "y": 0}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    combined = [[operator, [">", "x", 0], [">", "y", 0]] for operator in ("&", "|", "^", "==")]
    assert expressions(inputs[0]) == combined
    for expression in combined:
        assert sides(inputs, expression) == {True, False}, expression
    assert all(line["downgrades"] == [] for line in inputs)


# follow-booleans-and-chained-compares-meets-a-bool-literal
def test_meets_a_bool_literal() -> None:
    result = run_pyct(BOOL_LITERAL, '{"x": 0}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    # a bool is the int 1 or 0, and JSON writes it `true`
    assert expressions(inputs[0]) == [[">", ["+", "x", True], 5], ["==", "x", True]]
    assert '[">", ["+", "x", true], 5]' in result.stdout.splitlines()[0]
    fork_lines = [line for line in result.stderr.splitlines() if line.startswith("fork ")]
    assert fork_lines[:2] == [
        f"fork {BOOL_LITERAL_FILE}:2:7  x + True > 5  not taken",
        f"fork {BOOL_LITERAL_FILE}:4:7  x == True  not taken",
    ]
    values = [argument(line, "x") for line in inputs[1:]]
    assert any(value > 4 for value in values), values
    assert 1 in values


# follow-booleans-and-chained-compares-follows-membership-in-a-tuple-or-list
def test_follows_membership_in_a_tuple_or_list() -> None:
    result = run_pyct(MEMBERSHIP, '{"x": 0, "y": 0}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    # `in` compares with each element in turn, as Python does, until one holds
    assert [(fork["line"], fork["col"], fork["expression"]) for fork in forks_of(inputs[0])] == [
        (2, 7, ["==", "x", 1]),
        (2, 7, ["==", "x", 2]),
        (2, 7, ["==", "x", 3]),
        (4, 7, ["==", "y", 4]),
        (4, 7, ["==", "y", 5]),
    ]
    assert all(fork["taken"] is False for fork in forks_of(inputs[0]))
    assert {1, 2, 3} <= {argument(line, "x") for line in inputs}
    assert {4, 5} <= {argument(line, "y") for line in inputs}


# follow-booleans-and-chained-compares-records-a-truth-test-where-a-builtin-runs
def test_records_a_truth_test_where_a_builtin_runs() -> None:
    result = run_pyct(BUILTIN_TRUTH, '{"x": 0, "z": 0}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    # `bool()` makes its answer plain where it runs, so `if y:` has nothing left to record
    assert at(inputs[0], 2) == [["!=", "x", 0]]
    assert at(inputs[0], 4) == []
    assert at(inputs[0], 6) == [[">", "x", 5], [">", "z", 5]]
    for expression in (["!=", "x", 0], [">", "x", 5], [">", "z", 5]):
        assert sides(inputs, expression) == {True, False}, expression


# follow-booleans-and-chained-compares-leaves-an-untested-condition-alone
def test_leaves_an_untested_condition_alone() -> None:
    result = run_pyct(UNTESTED, '{"x": 0}')

    assert result.returncode == 0, result.stderr
    # the answer goes back to the caller untested, and pyct does not test a return value
    assert one_line(result.stdout)["forks"] == []
    assert summary_line(result.stdout)["stopped"] == "no fork to flip"


# follow-booleans-and-chained-compares-downgrades-an-untaught-bool-operation
def test_downgrades_an_untaught_bool_operation() -> None:
    result = run_pyct(UNTAUGHT, '{"x": 1}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    at = "targets/bools/untaught.py"
    assert seed["downgrades"] == [
        downgrade("__invert__", 1, f"{at}:3:4"),
        downgrade("__lshift__", 1, f"{at}:4:4"),
        downgrade("__and__", 1, f"{at}:5:4"),
        downgrade("__int__", 1, f"{at}:6:4"),
        # `str(b)` and the f-string's `{b}` are two sites on one line
        downgrade("__str__", 1, f"{at}:7:7"),
        downgrade("__format__", 1, f"{at}:7:30"),
    ]
    # `str(b)` and the f-string read `True`, so the `if b:` inside them runs and records the fork
    assert [(fork["line"], fork["expression"]) for fork in forks_of(seed)] == [(8, [">", "x", 0])]


# follow-booleans-and-chained-compares-finds-the-failing-assert
def test_finds_the_failing_assert() -> None:
    result = run_pyct(FAILING_ASSERT, '{"x": 5}')

    assert result.returncode == 0, result.stderr
    seed, solved = input_lines(result.stdout)[:2]
    assert [(fork["expression"], fork["taken"]) for fork in forks_of(seed)] == [
        ([">", "x", 3], True)
    ]
    assert argument(solved, "x") <= 3
    assert [(fork["expression"], fork["taken"]) for fork in forks_of(solved)] == [
        ([">", "x", 3], False)
    ]
    failure = failure_of(solved)
    assert failure["kind"] == "target_raised"
    assert "AssertionError" in str(failure["detail"])


# follow-booleans-and-chained-compares-finds-the-false-divisor
def test_finds_the_false_divisor() -> None:
    result = run_pyct(FALSE_DIVISOR, '{"x": 1}')

    assert result.returncode == 0, result.stderr
    seed, solved = input_lines(result.stdout)[:2]
    # the zero fork is the bool's own condition, as `if` would test it
    assert [(fork["line"], fork["expression"], fork["taken"]) for fork in forks_of(seed)] == [
        (2, [">", "x", 0], True)
    ]
    assert argument(solved, "x") <= 0
    assert [(fork["expression"], fork["taken"]) for fork in forks_of(solved)] == [
        ([">", "x", 0], False)
    ]
    failure = failure_of(solved)
    assert failure["kind"] == "target_raised"
    assert "ZeroDivisionError" in str(failure["detail"])


# follow-booleans-and-chained-compares-reports-a-compare-with-a-string
def test_reports_a_compare_with_a_string() -> None:
    result = run_pyct(COMPARE_WITH_STR, '{"x": 0}')

    assert result.returncode == 0, result.stderr
    seed = one_line(result.stdout)
    # `==` with a str is a plain False, as Python makes it; `<` with one raises in Python
    assert seed["forks"] == []
    assert seed["downgrades"] == []
    failure = failure_of(seed)
    assert failure["kind"] == "target_raised"
    assert "TypeError" in str(failure["detail"])
    assert summary_line(result.stdout)["stopped"] == "no fork to flip"

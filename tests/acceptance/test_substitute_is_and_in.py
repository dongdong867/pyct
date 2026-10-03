"""Acceptance tests for substitute-is-and-literal-in-at-the-call-site: what each substitution does.

Each test spawns ``python -P -m pyct`` through the harness. pyct substitutes `is True` and
`in` in every module of the target's top-level package as Python imports it, so only a run
through the command line proves the substitution holds where the target runs.
"""

import importlib.util
import sys
import types
from collections.abc import Iterator
from pathlib import Path

from tests.acceptance.harness import (
    REPO_ROOT,
    argument,
    first_line,
    forks_of,
    input_lines,
    run_pyct,
    summary_line,
)
from tests.acceptance.test_bools import at, expressions, failure_of, sides
from tests.acceptance.test_strs import text

INTERCEPT = REPO_ROOT / "targets" / "intercept"
IDENTITY = "targets.intercept.identity::check"
LITERAL_SET = "targets.intercept.literal_set::route"
IN_PLAIN_TEXT = "targets.intercept.in_plain_text::pick"
IN_WHERE_IT_RUNS = "targets.strs.in_where_it_runs::look"
IN_WHERE_IT_RUNS_FILE = str(REPO_ROOT / "targets" / "strs" / "in_where_it_runs.py")
POSITIONS = "targets.intercept.positions::place"
POSITIONS_FILE = INTERCEPT / "positions.py"
IDENTITIES = "targets.intercept.identities::sides"
IN_LIST = "targets.intercept.in_list::later"
PLAIN = "targets.intercept.plain::plain"
TYPE_ERRORS = "targets.intercept.type_errors"
OWN_CONTAINS = "targets.intercept.own_contains::look"


def covered_of(line: dict[str, object], file: Path) -> list[int]:
    """The lines one input covered in one file, narrowed so a comparison means something."""
    covered = line["covered"]
    assert isinstance(covered, dict), line
    return list(covered[str(file)])


def plain_lines(file: Path, function: str, *args: object) -> list[int]:
    """The lines a line tracer sees in the file while plain Python runs the function once.

    The module is loaded from its file under a name of its own, with Python's
    own loader, so nothing pyct does reaches it.
    """
    spec = importlib.util.spec_from_file_location(f"plain_{file.stem}", file)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monitoring = sys.monitoring
    tool = next(tool for tool in (3, 4, 5) if monitoring.get_tool(tool) is None)
    seen: set[int] = set()

    def on_line(code: types.CodeType, line: int) -> None:
        if code.co_filename == str(file):
            seen.add(line)

    monitoring.use_tool_id(tool, "plain lines")
    monitoring.register_callback(tool, monitoring.events.LINE, on_line)
    monitoring.set_events(tool, monitoring.events.LINE)
    try:
        getattr(module, function)(*args)
    finally:
        monitoring.set_events(tool, 0)
        monitoring.free_tool_id(tool)
    return sorted(seen)


def compiled_total(file: Path) -> int:
    """How many lines the compiler gives the file as written: every line its code objects name."""

    def walk(code: types.CodeType) -> Iterator[types.CodeType]:
        yield code
        for constant in code.co_consts:
            if isinstance(constant, types.CodeType):
                yield from walk(constant)

    code = compile(file.read_text(), str(file), "exec")
    return len({line for each in walk(code) for _, _, line in each.co_lines() if line})


# intercept-builtin-functions-takes-the-branch-python-takes-on-is-true
def test_takes_the_branch_python_takes_on_is_true() -> None:
    result = run_pyct(IDENTITY, '{"x": 10}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    seed = inputs[0]
    # plain Python: `x > 5` is True at 10, so `big is True` holds and "big" is returned
    assert covered_of(seed, INTERCEPT / "identity.py") == [2, 3, 4]
    assert [(fork["line"], fork["expression"], fork["taken"]) for fork in forks_of(seed)] == [
        (3, [">", "x", 5], True)
    ]
    solved = [line for line in inputs[1:] if 5 in covered_of(line, INTERCEPT / "identity.py")]
    assert solved, inputs
    assert all(argument(line, "x") <= 5 for line in solved)


# intercept-builtin-functions-follows-membership-in-a-literal-set
def test_follows_membership_in_a_literal_set() -> None:
    result = run_pyct(LITERAL_SET, '{"x": 0, "s": ""}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    written = [
        ["==", "x", 1],
        ["==", "x", 5],
        ["==", "x", 9],
        ["==", "s", "'GET'"],
        ["==", "s", "'POST'"],
    ]
    # one fork per element tried, in the order the code writes them, as a tuple records
    assert expressions(inputs[0]) == written
    assert all(fork["taken"] is False for fork in forks_of(inputs[0]))
    for expression in written:
        assert sides(inputs, expression) == {True, False}, expression


# intercept-builtin-functions-follows-a-tracked-string-in-a-plain-one
def test_follows_a_tracked_string_in_a_plain_one() -> None:
    result = run_pyct(IN_PLAIN_TEXT, '{"s": "x"}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    assert [(fork["expression"], fork["taken"]) for fork in forks_of(inputs[0])] == [
        (["in", "s", "'abc'"], False)
    ]
    assert inputs[0]["downgrades"] == []
    taken = [line for line in inputs[1:] if sides([line], ["in", "s", "'abc'"]) == {True}]
    assert taken, inputs
    assert all(text(line, "s") in "abc" for line in taken)


# intercept-builtin-functions-records-in-where-it-is-tested
def test_records_in_where_it_is_tested() -> None:
    result = run_pyct(IN_WHERE_IT_RUNS, '{"s": "x"}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    # `in` on a string hands back its answer with the condition, so `if y:` records the fork
    # and `y = "a" in s` records none; `not in` is its own operator
    assert forks_of(seed) == [
        {
            "file": IN_WHERE_IT_RUNS_FILE,
            "line": 3,
            "col": 7,
            "expression": ["in", "'a'", "s"],
            "taken": False,
        },
        {
            "file": IN_WHERE_IT_RUNS_FILE,
            "line": 5,
            "col": 7,
            "expression": ["not in", "'b'", "s"],
            "taken": True,
        },
    ]
    assert f"fork {IN_WHERE_IT_RUNS_FILE}:5:7  'b' not in s  taken" in result.stderr.splitlines()


# intercept-builtin-functions-substitutes-in-place
def test_substitutes_in_place() -> None:
    result = run_pyct(POSITIONS, '{"x": 0}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert [(fork["line"], fork["col"], fork["expression"]) for fork in forks_of(seed)] == [
        (5, 7, [">", "x", 5]),
        (7, 7, ["==", "x", 1]),
        (7, 7, ["==", "x", 5]),
    ]
    assert all(fork["taken"] is False for fork in forks_of(seed))
    for line in input_lines(result.stdout):
        assert covered_of(line, POSITIONS_FILE) == plain_lines(
            POSITIONS_FILE, "place", argument(line, "x")
        )
    total = summary_line(result.stdout)["total"]
    assert total == {str(POSITIONS_FILE): compiled_total(POSITIONS_FILE)}


# intercept-builtin-functions-answers-every-identity-as-python-does
def test_answers_every_identity_as_python_does() -> None:
    result = run_pyct(IDENTITIES, '{"x": 0}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    # at 0, `b` stands for False: `b is False` and `b is not True` hold, the other two do not
    assert covered_of(seed, INTERCEPT / "identities.py") == plain_lines(
        INTERCEPT / "identities.py", "sides", 0
    )
    for number in (4, 6, 8, 10):
        assert at(seed, number) == [[">", "x", 5]], number
    assert all(fork["taken"] is False for fork in forks_of(seed))


# intercept-builtin-functions-keeps-in-on-a-list-as-it-was
def test_keeps_in_on_a_list_as_it_was() -> None:
    result = run_pyct(IN_LIST, '{"s": "x"}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert at(seed, 2) == [["==", "s", "'a'"], ["==", "s", "'b'"]]
    assert all(fork["taken"] is False for fork in forks_of(seed))
    assert at(seed, 3) == []


# intercept-builtin-functions-changes-no-plain-membership-or-identity
def test_changes_no_plain_membership_or_identity() -> None:
    result = run_pyct(PLAIN, '{"n": 0}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert covered_of(seed, INTERCEPT / "plain.py") == plain_lines(
        INTERCEPT / "plain.py", "plain", 0
    )
    assert expressions(seed) == [[">", "n", 0]]
    assert seed["downgrades"] == []


# intercept-builtin-functions-leaves-a-membership-type-error-to-the-target
def test_leaves_a_membership_type_error_to_the_target() -> None:
    for target, seed_text in (("in_text", '{"n": 1}'), ("in_set", '{"items": [1]}')):
        result = run_pyct(f"{TYPE_ERRORS}::{target}", seed_text)

        assert result.returncode == 0, result.stderr
        failure = failure_of(first_line(result.stdout))
        assert failure["kind"] == "target_raised", target
        assert str(failure["detail"]).startswith("TypeError:"), target
        assert summary_line(result.stdout)["stopped"] == "no fork to flip", target


# intercept-builtin-functions-leaves-a-raise-in-the-targets-own-contains-to-the-target
def test_leaves_a_raise_in_the_targets_own_contains_to_the_target() -> None:
    result = run_pyct(OWN_CONTAINS, '{"x": 0}')

    assert result.returncode == 0, result.stderr
    failure = failure_of(first_line(result.stdout))
    assert failure["kind"] == "target_raised"
    assert str(failure["detail"]).startswith("ZeroDivisionError:")

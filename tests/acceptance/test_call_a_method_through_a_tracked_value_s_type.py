"""Acceptance tests for the call-a-method-through-a-tracked-value-s-type bug.

A method Python's range or a dict view type defines, called through `type(v)`, `v.__class__` or a
name spelled as Python's type, answers on a tracked range or view as plain Python answers, and
records what the same method records when called on the value directly. Any other receiver gets
Python's own method, its refusals included. Each test runs pyct through the command line and reads
plain Python's answer from the same fixture called on plain values in this test run.
"""

import ast
import types
from typing import Any

import pytest

from targets.types import through, through_own
from tests.acceptance.harness import (
    REPO_ROOT,
    argument,
    first_line,
    forks_of,
    input_lines,
    run_pyct,
)
from tests.acceptance.test_pass_keywords_through_a_downgrade import covered_in
from tests.acceptance.test_read_a_tracked_value_s_type_as_its_base_type import (
    line_of,
    python_raise,
    raised,
)

TARGET = "targets.types.through"
FILE = REPO_ROOT / "targets" / "types" / "through.py"
OWN_FILE = REPO_ROOT / "targets" / "types" / "through_own.py"
SEED = '{"n": 3, "d": {"k": 1}}'


def defined(kind: type) -> set[str]:
    """The methods a type defines that are called on a value, on this Python."""
    called = (types.WrapperDescriptorType, types.MethodDescriptorType)
    return {name for name, member in vars(kind).items() if isinstance(member, called)}


def written(function: str) -> set[str]:
    """The method names a fixture function calls."""
    tree = ast.parse(FILE.read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function)
    calls = (n for n in ast.walk(node) if isinstance(n, ast.Call))
    return {call.func.attr for call in calls if isinstance(call.func, ast.Attribute)}


# the seed's line is what a check reads, and a walk of a range of n goes on growing
SEED_FIRST = ("--plateau", "1")


def covers(target: str, seed: str, returned: str, missed: str, file: str = str(FILE)) -> dict:
    """Run the target and check the seed's line covers ``returned``, not ``missed``, and has no
    failure. The line comes back for more checks."""
    result = run_pyct(target, seed, *SEED_FIRST)

    assert result.returncode == 0, result.stderr
    line = first_line(result.stdout)
    assert line["failure"] is None, line
    function = target.rpartition("::")[2]
    covered = covered_in(line, file)
    path = REPO_ROOT / file
    assert line_of(path, f'return "{returned}"', function) in covered
    assert line_of(path, f'return "{missed}"', function) not in covered
    return line


# call-a-method-through-a-tracked-value-s-type-answers-a-range-s-methods-as-python
def test_answers_a_range_s_methods_as_python() -> None:
    for way in through.RANGE_WAYS:
        assert defined(range) <= written(way.__name__), way
    assert through.range_methods(3) == "same"
    covers(f"{TARGET}::range_methods", '{"n": 3}', "same", "differs")


# call-a-method-through-a-tracked-value-s-type-answers-a-view-s-methods-as-python
def test_answers_a_view_s_methods_as_python() -> None:
    for name, ways in through.VIEW_WAYS:
        python = type(getattr(through.PLAIN_DICT, name)())
        for way in ways:
            assert defined(python) <= written(way.__name__), way
    assert through.view_methods({"k": 1}) == "same"
    covers(f"{TARGET}::view_methods", '{"d": {"k": 1}}', "same", "differs")


def args_of(line: dict[str, object]) -> dict[str, Any]:
    """The arguments of a printed line, narrowed so a lookup means something."""
    arguments = line["args"]
    assert isinstance(arguments, dict), line
    return arguments


def recorded(line: dict, function: str) -> tuple[list[Any], list[Any]]:
    """A line's forks, by expression and side, and its downgrades, by name, count, and line
    counted from the function's own first line."""
    start = line_of(FILE, f"def {function}(")
    forks = [(fork["expression"], fork["taken"]) for fork in forks_of(line)]
    downgrades = line["downgrades"]
    assert isinstance(downgrades, list)
    lost = [(lost["name"], lost["count"], lost["line"] - start) for lost in downgrades]
    return forks, lost


# call-a-method-through-a-tracked-value-s-type-records-what-the-direct-call-records
def test_records_what_the_direct_call_records() -> None:
    lines = {}
    for function in ("through", "direct"):
        result = run_pyct(f"{TARGET}::{function}", SEED)
        assert result.returncode == 0, result.stderr
        lines[function] = first_line(result.stdout)
        assert lines[function]["failure"] is None, lines[function]

    through_forks, through_lost = recorded(lines["through"], "through")
    direct_forks, direct_lost = recorded(lines["direct"], "direct")
    assert through_forks == direct_forks and through_forks
    assert through_lost == direct_lost
    assert {name for name, _, _ in direct_lost} == {"__len__", "index", "isdisjoint"}


# call-a-method-through-a-tracked-value-s-type-follows-forks-through-the-type
def test_follows_forks_through_the_type() -> None:
    assert through.lookup({"k": 1}) == "missing" and through.lookup({"a": 1}) == "found"
    result = run_pyct(f"{TARGET}::lookup", '{"d": {"k": 1}}')
    assert result.returncode == 0, result.stderr
    seed, *solved = input_lines(result.stdout)
    assert [(f["expression"], f["taken"]) for f in forks_of(seed)] == [(["in", "'a'", "d"], False)]
    assert seed["downgrades"] == []
    found = line_of(FILE, 'return "found"', "lookup")
    assert any("a" in args_of(s)["d"] and found in covered_in(s, str(FILE)) for s in solved)


def test_follows_a_walk_through_the_type() -> None:
    assert through.walk(1) == "short" and through.walk(3) == "two"
    result = run_pyct(f"{TARGET}::walk", '{"n": 1}')
    assert result.returncode == 0, result.stderr
    seed, *solved = input_lines(result.stdout)
    assert [(f["expression"], f["taken"]) for f in forks_of(seed)] == [
        ([">", "n", 0], True),
        ([">", "n", 1], False),
    ]
    assert seed["downgrades"] == []
    two = line_of(FILE, 'return "two"', "walk")
    assert any(argument(s, "n") >= 3 and two in covered_in(s, str(FILE)) for s in solved)


# call-a-method-through-a-tracked-value-s-type-keeps-other-receivers-and-names-as-written
def test_keeps_other_receivers_and_names_as_written() -> None:
    assert through_own.kept(3, {"k": 1}) == "kept"
    line = covers("targets.types.through_own::kept", SEED, "kept", "changed", file=str(OWN_FILE))
    assert line["downgrades"] == []


# call-a-method-through-a-tracked-value-s-type-refuses-what-python-refuses-in-its-words
def test_refuses_what_python_refuses_in_its_words() -> None:
    plain = through.refusals(through.PLAIN, through.PLAIN_DICT)
    assert all(refusal is not None for refusal in plain), plain
    assert through.wrong(3, {"k": 1}) == "same"
    covers(f"{TARGET}::wrong", SEED, "same", "differs")


# call-a-method-through-a-tracked-value-s-type-reports-a-method-s-own-raise-as-the-target-s
@pytest.mark.parametrize(
    ("function", "seed", "plain"),
    [
        ("index", '{"n": 3}', lambda: range(3).index(99)),
        ("disjoint", '{"d": {"k": 1}}', lambda: {"k": 1}.keys().isdisjoint(5)),  # pyrefly: ignore
    ],
)
def test_reports_a_method_s_own_raise_as_the_target_s(function, seed, plain) -> None:
    result = run_pyct(f"{TARGET}::{function}", seed)

    assert result.returncode == 0, result.stderr
    raised(first_line(result.stdout), python_raise(plain))

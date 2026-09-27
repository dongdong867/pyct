"""Acceptance tests for the return-a-real-bool-from-a-bool-method bug.

Each test spawns ``python -P -m pyct`` through the harness. pyct hands the value of each
`return` in a `__bool__` method of the target's package to core as Python imports the module,
so only a run through the command line proves it. Plain Python's answers come from the same
fixtures, called in this test run.
"""

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from targets.bools import bool_method_raises, bool_methods
from tests.acceptance.harness import REPO_ROOT, first_line, input_lines, run_pyct
from tests.acceptance.test_bools import failure_of
from tests.acceptance.test_ints import argument, forks_of
from tests.acceptance.test_win_back_three_rows import covered_in

METHODS = "targets.bools.bool_methods"
METHODS_FILE = str(REPO_ROOT / "targets" / "bools" / "bool_methods.py")
RAISES = "targets.bools.bool_method_raises"
RAISES_FILE = str(REPO_ROOT / "targets" / "bools" / "bool_method_raises.py")
SCOPE = REPO_ROOT / "targets" / "scope"


def position(file: str, written: str, *, after: str = "") -> tuple[int, int]:
    """The line and 0-based column where ``written`` starts, on the first line holding it that
    comes after the first line holding ``after``."""
    lines = Path(file).read_text(encoding="utf-8").splitlines()
    start = next(index for index, line in enumerate(lines) if after in line)
    for index in range(start, len(lines)):
        if written in lines[index]:
            return index + 1, lines[index].index(written)
    raise AssertionError(f"{written!r} is not in {file}")


def sited(line: dict[str, object]) -> list[tuple[object, object, object, object]]:
    """Each fork on a printed line, by its line, column, expression and side."""
    return [
        (fork["line"], fork["col"], fork["expression"], fork["taken"]) for fork in forks_of(line)
    ]


def returns_covered(stdout: str, file: str, function: str) -> set[str]:
    """Which of the function's two returns, "yes" and "no", any input ran."""
    covered = covered_in(stdout, file)
    yes, _ = position(file, 'return "yes"', after=f"def {function}(")
    no, _ = position(file, 'return "no"', after=f"def {function}(")
    return {name for name, number in (("yes", yes), ("no", no)) if number in covered}


def answers(function: Callable[[int], str], stdout: str) -> dict[int, str]:
    """Plain Python's answer for each x the run tried."""
    return {argument(line, "x"): function(argument(line, "x")) for line in input_lines(stdout)}


def plain_error(call: Callable[[], object]) -> str:
    """What plain Python raises for ``call`` in this run, as the failure's detail writes it."""
    with pytest.raises(TypeError) as raised:
        call()
    return f"TypeError: {raised.value}"


def refusal_opening() -> str:
    """How plain Python's refusal of a non-bool from `__bool__` opens in this run, up to the
    type's name: its message for a method that returns an int, less the name `int`."""
    message = plain_error(lambda: bool(bool_method_raises.Num(1)))
    assert message.endswith(" int"), message
    return message.removesuffix("int")


# return-a-real-bool-from-a-bool-method-follows-bool-of-a-value
def test_follows_bool_of_a_value() -> None:
    result = run_pyct(f"{METHODS}::f", '{"x": 1}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert seed["failure"] is None, seed
    line, col = position(METHODS_FILE, "bool(self.v)")
    # the `if Box(x):` line tests a real bool, so it records nothing
    assert sited(seed) == [(line, col, ["!=", "x", 0], True)]
    assert returns_covered(result.stdout, METHODS_FILE, "f") == {"yes", "no"}
    assert answers(bool_methods.f, result.stdout) == {1: "yes", 0: "no"}


# return-a-real-bool-from-a-bool-method-follows-a-compare
def test_follows_a_compare() -> None:
    result = run_pyct(f"{METHODS}::g", '{"x": 1}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert seed["failure"] is None, seed
    line, col = position(METHODS_FILE, "self.v != 0", after="class Cmp")
    assert sited(seed) == [(line, col, ["!=", "x", 0], True)]
    assert returns_covered(result.stdout, METHODS_FILE, "g") == {"yes", "no"}
    assert answers(bool_methods.g, result.stdout) == {1: "yes", 0: "no"}


# return-a-real-bool-from-a-bool-method-leaves-a-plain-bool-alone
def test_leaves_a_plain_bool_alone() -> None:
    result = run_pyct(f"{METHODS}::h", '{"x": 1}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert seed["failure"] is None and seed["downgrades"] == [], seed
    line, col = position(METHODS_FILE, "x > 0", after="def h(")
    assert sited(seed) == [(line, col, [">", "x", 0], True)]
    assert returns_covered(result.stdout, METHODS_FILE, "h") == {"yes", "no"}
    assert (bool_methods.h(1), bool_methods.h(0)) == ("yes", "no")


# return-a-real-bool-from-a-bool-method-leaves-nested-functions-alone
@pytest.mark.parametrize(("function", "owner"), [("inner", "Inner"), ("picked", "Picked")])
def test_leaves_nested_functions_alone(function: str, owner: str) -> None:
    result = run_pyct(f"{METHODS}::{function}", '{"x": 1}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert seed["failure"] is None, seed
    # at the method's own `return`, and none at the nested function's or the lambda's line
    line, col = _own_return(owner)
    assert sited(seed) == [(line, col, ["!=", "x", 0], True)]
    assert returns_covered(result.stdout, METHODS_FILE, function) == {"yes", "no"}
    plain = getattr(bool_methods, function)
    assert (plain(1), plain(0)) == ("yes", "no")


def _own_return(owner: str) -> tuple[int, int]:
    """Where the value of the `return` the class's `__bool__` itself writes starts."""
    line, col = position(METHODS_FILE, "return pick()" if owner == "Picked" else "return check()")
    return line, col + len("return ")


# return-a-real-bool-from-a-bool-method-leaves-a-function-outside-a-class-alone
def test_leaves_a_function_outside_a_class_alone() -> None:
    result = run_pyct(f"{METHODS}::k", '{"x": 1}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert seed["failure"] is None, seed
    line, col = position(METHODS_FILE, "ok", after="if ok:")
    assert sited(seed) == [(line, col, ["!=", "x", 0], True)]
    assert returns_covered(result.stdout, METHODS_FILE, "k") == {"yes", "no"}


# return-a-real-bool-from-a-bool-method-reports-python-s-error-for-a-plain-non-bool
def test_reports_python_s_error_for_a_plain_non_bool() -> None:
    result = run_pyct(f"{RAISES}::p", '{"x": 1}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    failure = failure_of(seed)
    assert failure["kind"] == "target_raised"
    assert failure["detail"] == plain_error(lambda: bool(bool_method_raises.One()))
    line, col = position(RAISES_FILE, "x > 0", after="def p(")
    # the fork before the method, and none at its `return 1`
    assert sited(seed) == [(line, col, [">", "x", 0], True)]


# return-a-real-bool-from-a-bool-method-passes-a-tracked-int-through
def test_passes_a_tracked_int_through() -> None:
    result = run_pyct(f"{RAISES}::q", '{"x": 1}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    failure = failure_of(seed)
    assert failure["kind"] == "target_raised"
    assert str(failure["detail"]).startswith(refusal_opening()), failure
    returned, _ = position(RAISES_FILE, "return self.v")
    assert [fork for fork in forks_of(seed) if fork["line"] == returned] == []


# return-a-real-bool-from-a-bool-method-still-raises-outside-the-package
def test_still_raises_outside_the_package() -> None:
    # run from the folder that holds shop, the target's package, and helper, a module beside it
    result = run_pyct("shop.boxed::check", '{"x": 1}', cwd=SCOPE)

    assert result.returncode == 0, result.stderr
    failure = failure_of(first_line(result.stdout))
    assert failure["kind"] == "target_raised"
    assert str(failure["detail"]).startswith(refusal_opening()), failure
    plain = subprocess.run(
        [sys.executable, "-c", "from shop.boxed import check; print(check(1))"],
        cwd=SCOPE,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    assert plain.stdout == "yes\n"

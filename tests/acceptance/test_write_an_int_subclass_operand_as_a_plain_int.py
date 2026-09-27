"""Acceptance tests for the write-an-int-subclass-operand-as-a-plain-int bug.

Each test spawns ``python -P -m pyct`` through the harness: the fork line on stderr and the
solver's input are written by pyct's own process, and ``--in-process`` is the path that wrote
the target's object as it was, so only a real run shows which methods ran and what they wrote.
"""

import pytest

from targets.ints import own_subclass
from tests.acceptance.harness import (
    REPO_ROOT,
    first_line,
    input_lines,
    run_pyct,
    summary_line,
)
from tests.acceptance.test_pass_keywords_through_a_downgrade import covered_in
from tests.acceptance.test_strs import number

OWN_SUBCLASS = "targets.ints.own_subclass"
OWN_SUBCLASS_FILE = str(REPO_ROOT / "targets" / "ints" / "own_subclass.py")
# the `return "big"` under named's fork, the `return "high"` under level's, and rev's `return "big"`
BIG = 75
HIGH = 93
REV_BIG = 99
# what each of Marked's own methods writes when it runs
MARKER = "TARGET CODE"


def fork_lines(stderr: str) -> list[str]:
    """What each fork line on stderr tested, without its site or its side."""
    return [line.split("  ")[1] for line in stderr.splitlines() if line.startswith("fork ")]


def solver_lines(stdout: str) -> list[dict[str, object]]:
    """The inputs the solver produced, in order."""
    return [line for line in input_lines(stdout) if line["source"] == "solver"]


# write-an-int-subclass-operand-as-a-plain-int-writes-the-value
@pytest.mark.parametrize("isolation", [(), ("--in-process",)], ids=["isolated", "in-process"])
def test_writes_the_value(isolation: tuple[str, ...]) -> None:
    result = run_pyct(f"{OWN_SUBCLASS}::named", '{"x": 0}', *isolation)

    assert result.returncode == 0, result.stderr
    assert fork_lines(result.stderr)[0] == "x > 3"
    assert any(
        number(line, "x") > 3 and BIG in covered_in(line, OWN_SUBCLASS_FILE)
        for line in solver_lines(result.stdout)
    ), result.stdout
    assert summary_line(result.stdout)["stopped"] == "no fork to flip"


# write-an-int-subclass-operand-as-a-plain-int-runs-no-target-method
def test_runs_no_target_method() -> None:
    result = run_pyct(f"{OWN_SUBCLASS}::marked", '{"x": -5}', "--in-process")

    assert result.returncode == 0, result.stderr
    assert MARKER not in result.stderr
    assert fork_lines(result.stderr)[0] == "x > -3"
    assert any(number(line, "x") > -3 for line in solver_lines(result.stdout)), result.stdout


# write-an-int-subclass-operand-as-a-plain-int-writes-an-enum-member-by-value
def test_writes_an_enum_member_by_value() -> None:
    result = run_pyct(f"{OWN_SUBCLASS}::level", '{"x": 0}', "--in-process")

    assert result.returncode == 0, result.stderr
    # the fork line writes a sum under a compare bare, as Python's precedence reads it
    assert fork_lines(result.stderr)[0] == "x + 3 > 5"
    assert any(
        number(line, "x") > 2 and HIGH in covered_in(line, OWN_SUBCLASS_FILE)
        for line in solver_lines(result.stdout)
    ), result.stdout


# write-an-int-subclass-operand-as-a-plain-int-survives-a-repr-that-raises
def test_survives_a_repr_that_raises() -> None:
    result = run_pyct(f"{OWN_SUBCLASS}::touchy", '{"x": 0}', "--in-process")

    assert result.returncode == 0, result.stderr
    assert input_lines(result.stdout)[0]["failure"] is None
    assert fork_lines(result.stderr)[0] == "x > 3"
    assert any(number(line, "x") > 3 for line in solver_lines(result.stdout)), result.stdout
    assert "Traceback" not in result.stderr


# the Bug's expected behavior: an int subclass's own reflected method answers first, as Python asks
def test_asks_an_int_subclass_its_own_reflected_method_first() -> None:
    result = run_pyct(f"{OWN_SUBCLASS}::rev", '{"x": -5}', "--in-process")

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    # Rev's own reversed `__lt__` answers `-5 > Rev(3)`, as it does in plain Python
    assert own_subclass.rev(-5) == "big"
    assert REV_BIG in covered_in(seed, OWN_SUBCLASS_FILE)
    # its answer is a plain bool, so the condition is lost and the operation is named
    assert seed["forks"] == []
    assert seed["downgrades"] == [{"name": "__gt__", "count": 1}]
    assert summary_line(result.stdout)["stopped"] == "no fork to flip"

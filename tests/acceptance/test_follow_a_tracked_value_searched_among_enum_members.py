"""Acceptance tests for follow-a-tracked-value-searched-among-enum-members.

A tracked str, float or int searched in a tuple, a list or a deque is compared as
`value == element` beside an element Python would compare plainly, such as a StrEnum member, a
float-valued Enum member, or a float beside an int, so it records its fork, while an element
with its own `__eq__`, the tracked value itself, or a container with its own `__contains__`
answers as Python has it answer. Each test runs pyct through the command line and checks the
seed's side against the same call in plain Python.
"""

import pytest

from targets.floats import searched_members as float_members
from targets.ints import searched_deques, searched_floats
from targets.strs import searched_members as str_members
from tests.acceptance.harness import REPO_ROOT, first_line, input_lines, run_pyct
from tests.acceptance.test_bool_parameters import covered
from tests.acceptance.test_bools import failure_of
from tests.acceptance.test_follow_an_int_subclass_on_the_left import placed
from tests.acceptance.test_write_an_int_subclass_operand_as_a_plain_int import (
    fork_lines,
    solver_lines,
)

STRS = "targets.strs.searched_members"
STRS_FILE = str(REPO_ROOT / "targets" / "strs" / "searched_members.py")
FLOATS = "targets.floats.searched_members"
FLOATS_FILE = str(REPO_ROOT / "targets" / "floats" / "searched_members.py")
AMONG_FLOATS = "targets.ints.searched_floats"
AMONG_FLOATS_FILE = str(REPO_ROOT / "targets" / "ints" / "searched_floats.py")
DEQUES = "targets.ints.searched_deques"
DEQUES_FILE = str(REPO_ROOT / "targets" / "ints" / "searched_deques.py")
# the line of each function's `in`, and of the return under its true side
COLORS, COLORS_TRUE = 33, 34
MODES, MODES_TRUE = 39, 40
NOT_TAGGED, NOT_TAGGED_TRUE = 45, 46
ITSELF_TRUE = 52
TOUCHY = 57
RATIOS, RATIOS_TRUE = 13, 14
FLOATS_IN, FLOATS_TRUE = 12, 13
FLOAT_MEMBERS_IN, FLOAT_MEMBERS_TRUE = 18, 19
NOT_QUEUED, NOT_QUEUED_TRUE = 23, 24
RING_TRUE = 30


def given(line: dict[str, object], name: str) -> object:
    """One argument off a printed line, of whatever type it has."""
    args = line["args"]
    assert isinstance(args, dict), line
    return args[name]


def no_downgrade(stdout: str) -> bool:
    """Whether no printed line lists a downgrade."""
    return all(line["downgrades"] == [] for line in input_lines(stdout))


# follow-a-tracked-value-searched-among-enum-members-follows-a-str-among-str-members
@pytest.mark.parametrize(
    ("function", "at", "true_line"),
    [("colors", COLORS, COLORS_TRUE), ("modes", MODES, MODES_TRUE)],
)
def test_follows_a_str_among_str_members(function: str, at: int, true_line: int) -> None:
    result = run_pyct(f"{STRS}::{function}", '{"s": "x"}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert getattr(str_members, function)("x") == "unknown"
    assert placed(seed, at) == [(["==", "s", "'red'"], False), (["==", "s", "'blue'"], False)]
    assert true_line + 1 in covered(seed, STRS_FILE)
    assert fork_lines(result.stderr)[:2] == ["s == 'red'", "s == 'blue'"]
    for value in ("red", "blue"):
        assert any(
            given(line, "s") == value and true_line in covered(line, STRS_FILE)
            for line in solver_lines(result.stdout)
        ), (value, result.stdout)
    assert no_downgrade(result.stdout), result.stdout


# follow-a-tracked-value-searched-among-enum-members-follows-a-float-among-float-members
def test_follows_a_float_among_float_members() -> None:
    result = run_pyct(f"{FLOATS}::ratios", '{"f": 3.0}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert float_members.ratios(3.0) == "unknown"
    assert placed(seed, RATIOS) == [(["==", "f", 0.5], False), (["==", "f", 1.0], False)]
    assert RATIOS_TRUE + 1 in covered(seed, FLOATS_FILE)
    for value in (0.5, 1.0):
        assert any(
            given(line, "f") == value and RATIOS_TRUE in covered(line, FLOATS_FILE)
            for line in solver_lines(result.stdout)
        ), (value, result.stdout)
    assert no_downgrade(result.stdout), result.stdout


# follow-a-tracked-value-searched-among-enum-members-follows-not-in-a-deque
def test_follows_not_in_a_deque() -> None:
    result = run_pyct(f"{DEQUES}::not_queued", '{"x": 1}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert searched_deques.not_queued(1) == "queued"
    assert placed(seed, NOT_QUEUED) == [(["==", "x", 0], False), (["==", "x", 1], True)]
    assert NOT_QUEUED_TRUE + 1 in covered(seed, DEQUES_FILE)
    solved = solver_lines(result.stdout)
    assert any(given(line, "x") == 0 for line in solved), result.stdout
    assert any(
        given(line, "x") not in (0, 1) and NOT_QUEUED_TRUE in covered(line, DEQUES_FILE)
        for line in solved
    ), result.stdout


# follow-a-tracked-value-searched-among-enum-members-follows-an-int-among-floats
@pytest.mark.parametrize(
    ("function", "at", "true_line"),
    [("floats", FLOATS_IN, FLOATS_TRUE), ("ratios", FLOAT_MEMBERS_IN, FLOAT_MEMBERS_TRUE)],
)
def test_follows_an_int_among_floats(function: str, at: int, true_line: int) -> None:
    result = run_pyct(f"{AMONG_FLOATS}::{function}", '{"x": 7}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert getattr(searched_floats, function)(7) == "unknown"
    assert placed(seed, at) == [(["==", "x", 0.5], False), (["==", "x", 2.0], False)]
    assert true_line + 1 in covered(seed, AMONG_FLOATS_FILE)
    # no int equals 0.5, so the first fork cannot flip
    assert f"missed {AMONG_FLOATS_FILE}:{at}:7 unsat" in result.stderr.splitlines(), result.stderr
    assert any(
        given(line, "x") == 2 and true_line in covered(line, AMONG_FLOATS_FILE)
        for line in solver_lines(result.stdout)
    ), result.stdout


# follow-a-tracked-value-searched-among-enum-members-follows-a-str-subclass-in-a-name
def test_follows_a_str_subclass_in_a_name() -> None:
    result = run_pyct(f"{STRS}::not_tagged", '{"s": "a"}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert str_members.not_tagged("a") == "tagged"
    assert placed(seed, NOT_TAGGED) == [(["==", "s", "'a'"], True)]
    assert NOT_TAGGED_TRUE + 1 in covered(seed, STRS_FILE)
    solved = solver_lines(result.stdout)
    assert any(
        placed(line, NOT_TAGGED)[:2] == [(["==", "s", "'a'"], False), (["==", "s", "'b'"], True)]
        for line in solved
    ), result.stdout
    assert any(given(line, "s") == "b" for line in solved), result.stdout


# follow-a-tracked-value-searched-among-enum-members-answers-by-identity
def test_answers_by_identity() -> None:
    result = run_pyct(f"{STRS}::itself", '{"s": "x"}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert str_members.itself("x") == "found"
    assert ITSELF_TRUE in covered(seed, STRS_FILE)
    assert seed["forks"] == []


# follow-a-tracked-value-searched-among-enum-members-asks-a-deque-s-own-contains
def test_asks_a_deque_s_own_contains() -> None:
    result = run_pyct(f"{DEQUES}::ring", '{"x": 7}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert searched_deques.ring(7) == "found"
    assert RING_TRUE in covered(seed, DEQUES_FILE)
    assert seed["forks"] == []


# follow-a-tracked-value-searched-among-enum-members-raises-where-an-element-s-eq-raises
def test_raises_where_an_element_s_eq_raises() -> None:
    result = run_pyct(f"{STRS}::touchy", '{"s": "x"}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    with pytest.raises(ValueError) as raised:
        str_members.touchy("x")
    assert placed(seed, TOUCHY) == [(["==", "s", "'red'"], False)]
    failure = failure_of(seed)
    assert failure["kind"] == "target_raised"
    assert failure["detail"] == f"ValueError: {raised.value}"

"""Acceptance tests for follow-an-int-subclass-on-the-left.

A tracked int searched in a tuple or a list of int subclass values, such as IntEnum members or
True, is compared as `x == element`, so it records its fork, while an element with its own
`__eq__`, or the tracked value itself, answers as Python has it answer. Each test runs pyct
through the command line and checks the seed's side against the same call in plain Python.
"""

import pytest

from targets.ints import searched_members
from tests.acceptance.harness import REPO_ROOT, first_line, input_lines, run_pyct
from tests.acceptance.test_bool_parameters import covered
from tests.acceptance.test_bools import failure_of
from tests.acceptance.test_ints import argument, forks_of
from tests.acceptance.test_write_an_int_subclass_operand_as_a_plain_int import (
    fork_lines,
    solver_lines,
)

SEARCHED = "targets.ints.searched_members"
SEARCHED_FILE = str(REPO_ROOT / "targets" / "ints" / "searched_members.py")
# the line of each function's `in`, and of the return under its true side
MEMBERS, MEMBERS_TRUE = 38, 39
NOT_KNOWN, NOT_KNOWN_TRUE = 44, 45
BOOLS, BOOLS_TRUE = 50, 51
CHAINED, CHAINED_TRUE = 56, 57
ODD, ODD_TRUE = 62, 63
ITSELF, ITSELF_TRUE = 68, 69
TOUCHY = 74


def placed(line: dict[str, object], number: int) -> list[tuple[object, object]]:
    """The expression and side of each fork a printed line lists at one line of the fixture."""
    return [
        (fork["expression"], fork["taken"]) for fork in forks_of(line) if fork["line"] == number
    ]


# follow-an-int-subclass-on-the-left-follows-membership-among-enum-members
def test_follows_membership_among_enum_members() -> None:
    result = run_pyct(f"{SEARCHED}::members", '{"x": 7}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert searched_members.members(7) == "unknown"
    assert placed(seed, MEMBERS) == [(["==", "x", 0], False), (["==", "x", 1], False)]
    assert fork_lines(result.stderr)[:2] == ["x == 0", "x == 1"]
    for value in (0, 1):
        assert any(
            argument(line, "x") == value and MEMBERS_TRUE in covered(line, SEARCHED_FILE)
            for line in solver_lines(result.stdout)
        ), (value, result.stdout)
    assert all(line["downgrades"] == [] for line in input_lines(result.stdout))


# follow-an-int-subclass-on-the-left-follows-not-in-a-list-held-in-a-name
def test_follows_not_in_a_list_held_in_a_name() -> None:
    result = run_pyct(f"{SEARCHED}::not_known", '{"x": 1}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    # `not in` records the same forks as `in`, and plain Python finds 1 among the members
    assert placed(seed, NOT_KNOWN) == [(["==", "x", 1], True)]
    assert searched_members.not_known(1) == "known"
    assert NOT_KNOWN_TRUE + 1 in covered(seed, SEARCHED_FILE)
    solved = solver_lines(result.stdout)
    assert any(
        placed(line, NOT_KNOWN)[:2] == [(["==", "x", 1], False), (["==", "x", 3], False)]
        for line in solved
    ), result.stdout
    assert any(argument(line, "x") == 3 for line in solved), result.stdout


# follow-an-int-subclass-on-the-left-follows-a-bool-in-a-tuple
def test_follows_a_bool_in_a_tuple() -> None:
    result = run_pyct(f"{SEARCHED}::bools", '{"x": 1}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert searched_members.bools(1) == "found"
    assert placed(seed, BOOLS) == [(["==", "x", True], True)]
    assert '["==", "x", true]' in result.stdout.splitlines()[0]
    assert fork_lines(result.stderr)[0] == "x == True"
    solved = solver_lines(result.stdout)
    assert any(
        placed(line, BOOLS) == [(["==", "x", True], False), (["==", "x", 3], True)]
        for line in solved
    ), result.stdout
    assert any(argument(line, "x") == 3 for line in solved), result.stdout


# follow-an-int-subclass-on-the-left-follows-a-link-of-a-chain
def test_follows_a_link_of_a_chain() -> None:
    result = run_pyct(f"{SEARCHED}::chained", '{"x": 7}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert searched_members.chained(7) == "unknown"
    assert placed(seed, CHAINED) == [
        ([">=", "x", 0], True),
        (["==", "x", 0], False),
        (["==", "x", 1], False),
    ]
    assert any(
        argument(line, "x") == 1 and CHAINED_TRUE in covered(line, SEARCHED_FILE)
        for line in solver_lines(result.stdout)
    ), result.stdout


# follow-an-int-subclass-on-the-left-lets-a-member-s-own-eq-answer
def test_lets_a_member_s_own_eq_answer() -> None:
    result = run_pyct(f"{SEARCHED}::odd", '{"x": 4}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert searched_members.odd(4) == "even"
    # Odd's own `__eq__` answers, as Python asks it, and the `in` tests what it answered
    assert placed(seed, ODD) == [(["==", ["%", "x", 2], 1], False)]
    assert ["==", "x", 1] not in [fork["expression"] for fork in forks_of(seed)]
    assert any(
        argument(line, "x") % 2 == 1 and ODD_TRUE in covered(line, SEARCHED_FILE)
        for line in solver_lines(result.stdout)
    ), result.stdout


# follow-an-int-subclass-on-the-left-answers-by-identity
def test_answers_by_identity() -> None:
    result = run_pyct(f"{SEARCHED}::itself", '{"x": 7}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert searched_members.itself(7) == "found"
    assert ITSELF_TRUE in covered(seed, SEARCHED_FILE)
    assert seed["forks"] == []


# follow-an-int-subclass-on-the-left-raises-where-a-member-s-eq-raises
def test_raises_where_a_member_s_eq_raises() -> None:
    result = run_pyct(f"{SEARCHED}::touchy", '{"x": 7}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    with pytest.raises(ValueError) as raised:
        searched_members.touchy(7)
    assert placed(seed, TOUCHY) == [(["==", "x", 0], False)]
    failure = failure_of(seed)
    assert failure["kind"] == "target_raised"
    assert failure["detail"] == f"ValueError: {raised.value}"

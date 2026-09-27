"""Acceptance tests for the survive-a-pickle-round-trip bug.

Each test spawns ``python -P -m pyct`` through the harness: the bug was a target that
pickles a tracked value reported as raising, and only a real run shows what the target
loads back, which forks reach the line and which downgrades it names.
"""

import pickle

import pytest

from tests.acceptance.harness import REPO_ROOT, first_line, one_line, run_pyct, second_line
from tests.acceptance.test_pass_keywords_through_a_downgrade import covered_in
from tests.acceptance.test_strs import forks_of, number

PICKLED = "targets.ints.pickled"
PICKLED_FILE = str(REPO_ROOT / "targets" / "ints" / "pickled.py")
# the `return "small"` of round_trip, and the line under each of each_type's three checks
ROUND_TRIP_SMALL = 9
UNDER_EACH_TYPE = [25, 27, 29]
# the fork after the pickle in pickle_then_check, and the one after the copy in copied
AFTER_THE_PICKLE = {"file": PICKLED_FILE, "line": 14, "col": 7, "expression": [">", "n", 10]}
AFTER_THE_COPY = {"file": PICKLED_FILE, "line": 51, "col": 7, "expression": [">", "n", 10]}


# survive-a-pickle-round-trip-hands-back-the-plain-value
def test_hands_back_the_plain_value() -> None:
    result = run_pyct(f"{PICKLED}::round_trip", '{"n": 3}')

    assert result.returncode == 0, result.stderr
    # the load hands back a plain int, so the compare after it is Python's own
    seed = one_line(result.stdout)
    assert seed["failure"] is None
    assert seed["forks"] == []
    assert seed["downgrades"] == [{"name": "__reduce_ex__", "count": 1}]
    assert ROUND_TRIP_SMALL in covered_in(seed, PICKLED_FILE)


# survive-a-pickle-round-trip-keeps-the-pickled-value-tracked
def test_keeps_the_pickled_value_tracked() -> None:
    result = run_pyct(f"{PICKLED}::pickle_then_check", '{"n": 3}')

    assert result.returncode == 0, result.stderr
    seed, solved = first_line(result.stdout), second_line(result.stdout)
    assert forks_of(seed) == [{**AFTER_THE_PICKLE, "taken": False}]
    assert seed["downgrades"] == [{"name": "__reduce_ex__", "count": 1}]
    assert number(solved, "n") > 10
    assert forks_of(solved) == [{**AFTER_THE_PICKLE, "taken": True}]


# survive-a-pickle-round-trip-loads-each-type-as-python-would
def test_loads_each_type_as_python_would() -> None:
    result = run_pyct(f"{PICKLED}::each_type", '{"n": 3, "s": "ab"}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert seed["failure"] is None
    # an int, a bool and a str, each Python's own, so every check holds
    assert set(UNDER_EACH_TYPE) <= set(covered_in(seed, PICKLED_FILE))
    # one call for each of the three values, one after another, so one entry counts them
    assert seed["downgrades"] == [{"name": "__reduce_ex__", "count": 3}]


# survive-a-pickle-round-trip-pickles-the-same-at-every-protocol
def test_pickles_the_same_at_every_protocol() -> None:
    result = run_pyct(f"{PICKLED}::every_protocol", '{"n": 3}')

    assert result.returncode == 0, result.stderr
    seed = one_line(result.stdout)
    assert seed["failure"] is None
    assert seed["forks"] == []
    # one call for each protocol from 0 up, and nothing else lost the condition
    protocols = pickle.HIGHEST_PROTOCOL + 1
    assert seed["downgrades"] == [{"name": "__reduce_ex__", "count": protocols}]


# survive-a-pickle-round-trip-counts-each-tracked-value-in-a-container
def test_counts_each_tracked_value_in_a_container() -> None:
    result = run_pyct(f"{PICKLED}::in_a_container", '{"n": 3, "s": "ab"}')

    assert result.returncode == 0, result.stderr
    seed = one_line(result.stdout)
    assert seed["failure"] is None
    assert seed["forks"] == []
    # n and s are written, and the plain 1 beside them loses nothing
    assert seed["downgrades"] == [{"name": "__reduce_ex__", "count": 2}]


# survive-a-pickle-round-trip-leaves-a-copy-the-value-itself
def test_leaves_a_copy_the_value_itself() -> None:
    result = run_pyct(f"{PICKLED}::copied", '{"n": 3}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert forks_of(seed) == [{**AFTER_THE_COPY, "taken": False}]
    assert seed["downgrades"] == []


# survive-a-pickle-round-trip-raises-what-python-raises
def test_raises_what_python_raises() -> None:
    result = run_pyct(f"{PICKLED}::past_the_highest_protocol", '{"n": 3}')

    assert result.returncode == 0, result.stderr
    seed = one_line(result.stdout)
    # pickle refuses the protocol before it writes anything, on a plain int as on a tracked one
    with pytest.raises(ValueError) as plain:
        pickle.dumps(3, protocol=99)
    assert seed["failure"] == {"kind": "target_raised", "detail": f"ValueError: {plain.value}"}
    assert seed["downgrades"] == []

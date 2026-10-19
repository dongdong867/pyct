"""Acceptance tests for the `repeat` part of close-four-small-v1-gaps: a tracked str times a
plain int is a tracked str, up to the bound.

Each test spawns ``python -P -m pyct`` through the harness: the repeat is followed only if the
fork on it reaches the solver and the solver's answer, run by plain Python, takes the other side.
"""

from collections.abc import Callable

import pytest

from pyct.core.str_repeats import MOST_COPIES
from targets.strs import repeats
from tests.acceptance.harness import REPO_ROOT, input_lines, run_pyct
from tests.acceptance.test_fork_on_a_split_s_count_before_it_unpacks import (
    line_of as line_in,
)
from tests.acceptance.test_fork_on_a_split_s_count_before_it_unpacks import raised_by_python
from tests.acceptance.test_lists import (
    args_of,
    downgrade_names,
    failure_detail,
    fork_line,
    listed,
    solved,
)

REPEATS = "targets.strs.repeats"
REPEATS_FILE = str(REPO_ROOT / "targets" / "strs" / "repeats.py")


def line_of(text: str, function: str) -> int:
    return line_in(text, REPEATS_FILE, after=f"def {function}(")


def covered_by(line: dict[str, object], number: int) -> bool:
    covered = line["covered"]
    assert isinstance(covered, dict), line
    return number in covered.get(REPEATS_FILE, [])


def reaches_one(function: str, seed: str) -> list[dict[str, object]]:
    """The lines of a run on the function, which a solver input must take to its `return 1`."""
    result = run_pyct(f"{REPEATS}::{function}", seed)
    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    one = line_of("return 1", function)
    assert any(covered_by(line, one) for line in solved(lines)), lines
    return lines


# close-four-small-v1-gaps-repeat-follows-a-plain-count
def test_follows_a_plain_count() -> None:
    result = run_pyct(f"{REPEATS}::twice", '{"s": ""}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    at = line_of('if s * 2 == "abab":', "twice")
    assert listed(lines[0]) == [(at, ["==", ["*", "s", 2], "'abab'"], False)]
    assert lines[0]["downgrades"] == []
    assert fork_line(result.stderr, REPEATS_FILE, at, "s * 2 == 'abab'", False)
    one = line_of("return 1", "twice")
    assert any(args_of(line)["s"] == "ab" and covered_by(line, one) for line in solved(lines))


# close-four-small-v1-gaps-repeat-follows-a-count-on-the-left
def test_follows_a_count_on_the_left() -> None:
    result = run_pyct(f"{REPEATS}::on_the_left", '{"s": ""}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    at = line_of('if t.startswith("xyx"):', "on_the_left")
    assert listed(lines[0]) == [(at, ["startswith", ["*", 3, "s"], "'xyx'"], False)]
    assert fork_line(result.stderr, REPEATS_FILE, at, "(3 * s).startswith('xyx')", False)
    one = line_of("return 1", "on_the_left")
    assert any(covered_by(line, one) for line in solved(lines)), lines


# close-four-small-v1-gaps-repeat-follows-each-plain-count-up-to-the-bound
@pytest.mark.parametrize(
    ("function", "fork"),
    [
        ("by_a_bool", ["==", ["*", "s", 1], "'a'"]),
        ("in_place", ["==", ["len", ["*", "s", 2]], 6]),
        ("at_the_bound", ["==", ["*", "s", MOST_COPIES], repr("ab" * MOST_COPIES)]),
    ],
)
def test_follows_each_plain_count_up_to_the_bound(function: str, fork: list[object]) -> None:
    lines = reaches_one(function, '{"s": ""}')

    assert listed(lines[0])[0][1:] == (fork, False)
    assert lines[0]["downgrades"] == []


# close-four-small-v1-gaps-repeat-gives-nothing-plain-for-no-copies
def test_gives_nothing_plain_for_no_copies() -> None:
    result = run_pyct(f"{REPEATS}::nothing", '{"s": "ab"}')

    assert result.returncode == 0, result.stderr
    (line,) = input_lines(result.stdout)
    assert listed(line) == [] and line["downgrades"] == []
    assert covered_by(line, line_of("return 1", "nothing"))


# close-four-small-v1-gaps-repeat-downgrades-past-the-bound-and-a-tracked-count
@pytest.mark.parametrize(
    ("target", "seed", "name"),
    [
        ("targets.strs.repeat_past_the_bound::past_the_bound", '{"s": ""}', "__mul__"),
        (f"{REPEATS}::tracked_count", '{"s": "", "n": 2}', "__mul__"),
    ],
)
def test_downgrades_past_the_bound_and_a_tracked_count(target: str, seed: str, name: str) -> None:
    result = run_pyct(target, seed)

    assert result.returncode == 0, result.stderr
    line = input_lines(result.stdout)[0]
    assert listed(line) == []
    assert downgrade_names(line) == [name]


# close-four-small-v1-gaps-repeat-raises-python-s-error
@pytest.mark.parametrize(
    ("function", "call"),
    [
        ("by_a_float", lambda: repeats.by_a_float("ab")),
        ("too_many", lambda: repeats.too_many("ab")),
    ],
)
def test_raises_python_s_error(function: str, call: Callable[[], object]) -> None:
    result = run_pyct(f"{REPEATS}::{function}", '{"s": "ab"}')

    assert result.returncode == 0, result.stderr
    line = input_lines(result.stdout)[0]
    assert failure_detail(line) == raised_by_python(call)

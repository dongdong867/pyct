"""Acceptance tests for the `range` part of close-four-small-v1-gaps: `len` of a tracked range
is Python's count, tracked.

Each test spawns ``python -P -m pyct`` through the harness: the length is followed only if the
fork on it reaches the solver and the solver's answer, run by plain Python, takes the other side.
"""

from collections.abc import Callable

import pytest

from targets.ranges import lengths
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

LENGTHS = "targets.ranges.lengths"
LENGTHS_FILE = str(REPO_ROOT / "targets" / "ranges" / "lengths.py")


def line_of(text: str, function: str) -> int:
    return line_in(text, LENGTHS_FILE, after=f"def {function}(")


def covered_by(line: dict[str, object], number: int) -> bool:
    covered = line["covered"]
    assert isinstance(covered, dict), line
    return number in covered.get(LENGTHS_FILE, [])


# close-four-small-v1-gaps-range-follows-its-length
def test_follows_its_length() -> None:
    result = run_pyct(f"{LENGTHS}::counted", '{"n": 0}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    at = line_of("if len(range(n)) == 5:", "counted")
    assert listed(lines[0]) == [(at, ["==", ["len", ["range", 0, "n"]], 5], False)]
    assert lines[0]["downgrades"] == []
    assert fork_line(result.stderr, LENGTHS_FILE, at, "len(range(0, n)) == 5", False)
    one = line_of("return 1", "counted")
    assert any(args_of(line)["n"] == 5 and covered_by(line, one) for line in solved(lines))


# close-four-small-v1-gaps-range-counts-as-python-does
@pytest.mark.parametrize(
    ("function", "seed", "check"),
    [
        ("stepped_down", '{"a": 0, "b": 0}', lambda a, b: len(range(a, b, -3)) == 4),
        ("emptied", '{"a": 0}', lambda a: len(range(a, 10, 2)) == 0),
        ("tracked_step", '{"k": 1}', lambda k: len(range(0, 20, k)) == 3),
    ],
)
def test_counts_as_python_does(function: str, seed: str, check: Callable[..., bool]) -> None:
    result = run_pyct(f"{LENGTHS}::{function}", seed)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert lines[0]["downgrades"] == []
    one = line_of("return 1", function)
    reached = [line for line in solved(lines) if covered_by(line, one)]
    assert reached, lines
    # the solver's answer takes the side plain Python takes on it
    assert all(check(**args_of(line)) for line in reached)


# close-four-small-v1-gaps-range-keeps-a-direct-call-a-downgrade
def test_keeps_a_direct_call_a_downgrade() -> None:
    result = run_pyct(f"{LENGTHS}::called_directly", '{"n": 3}')

    assert result.returncode == 0, result.stderr
    assert downgrade_names(input_lines(result.stdout)[0]) == ["__len__"]


# close-four-small-v1-gaps-range-raises-python-s-error
def test_raises_python_s_error() -> None:
    result = run_pyct(f"{LENGTHS}::too_long", '{"n": 0}')

    assert result.returncode == 0, result.stderr
    line = input_lines(result.stdout)[0]
    assert failure_detail(line) == raised_by_python(lambda: lengths.too_long(0))
    assert downgrade_names(line) == []

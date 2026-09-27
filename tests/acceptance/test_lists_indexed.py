"""Acceptance tests for follow-lists-as-they-change beyond one criterion each: a plain index
into items of two kinds, a list inside a list read from the end or at a tracked index, and a
list changed in place many times, each through the command line."""

import json
import time

import pytest

from tests.acceptance.harness import input_lines, run_pyct
from tests.acceptance.test_lists import UNTIL_NO_GAIN, forks_of, sides_of, solved

MIXED = "targets.lists.mixed"


# follow-lists-and-dicts-as-they-change-follows-a-tracked-index: a plain index into a list of
# items of two kinds is written as indexed and followed, only a tracked one is a downgrade
@pytest.mark.parametrize(
    ("function", "seed", "fork"),
    [
        ("last_is_a", [1, "b"], ["==", ["[]", "items", -1], "'a'"]),
        ("first_after_append", [1, "b"], [">", ["[]", ["+", "items", ["[,]", 5]], 0], 3]),
    ],
)
def test_a_plain_index_into_items_of_two_kinds_is_followed(
    function: str, seed: list[object], fork: list[object]
) -> None:
    result = run_pyct(f"{MIXED}::{function}", json.dumps({"items": seed}))

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert lines[0]["downgrades"] == [], lines[0]
    assert (json.dumps(fork), True) in sides_of(lines), sides_of(lines)
    assert [line["mismatch_at"] for line in solved(lines)] == [None] * len(solved(lines))


# follow-lists-and-dicts-as-they-change-follows-lists-inside-lists: a list inside a list is
# written as the target indexed it, so its forks follow the outer list's length and the index
@pytest.mark.parametrize(
    ("function", "seed", "fork"),
    [
        ("last_row", {"grid": [[1], [2]]}, [">", ["[]", ["[]", "grid", -1], 0], 5]),
        ("row_at", {"grid": [[1], [2]], "i": 0}, [">", ["[]", ["[]", "grid", "i"], 0], 5]),
    ],
)
def test_a_list_inside_a_list_is_written_as_indexed(
    function: str, seed: dict[str, object], fork: list[object]
) -> None:
    result = run_pyct(f"targets.lists.rows::{function}", json.dumps(seed), *UNTIL_NO_GAIN)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert {(json.dumps(fork), True), (json.dumps(fork), False)} <= sides_of(lines)
    assert [line["mismatch_at"] for line in solved(lines)] == [None] * len(solved(lines))


IN_PLACE = "targets.lists.in_place"


# follow-lists-and-dicts-as-they-change-follows-every-list-change: a list changed in place many
# times reads back as fast as it was changed, and a run stays inside its budget
@pytest.mark.parametrize(
    ("function", "seed", "fork"),
    [
        ("tally", {"counts": [0, 0], "n": 3}, 5),
        ("swaps", {"pair": [1, 2]}, 5),
    ],
)
def test_a_list_changed_in_place_many_times_is_flipped_inside_the_budget(
    function: str, seed: dict[str, object], fork: int
) -> None:
    started = time.monotonic()
    result = run_pyct(f"{IN_PLACE}::{function}", json.dumps(seed), "--budget", "10")
    elapsed = time.monotonic() - started

    assert result.returncode == 0, result.stderr
    assert elapsed < 12, elapsed
    lines = input_lines(result.stdout)
    last = [forks_of(line)[-1] for line in lines]
    assert {fork["taken"] for fork in last if fork["line"] == fork_line_of(function)} == {
        True,
        False,
    }
    assert [line["mismatch_at"] for line in solved(lines)] == [None] * len(solved(lines))


def fork_line_of(function: str) -> int:
    """The line of the fork after the changes, in targets/lists/in_place.py."""
    return {"tally": 4, "swaps": 12}[function]

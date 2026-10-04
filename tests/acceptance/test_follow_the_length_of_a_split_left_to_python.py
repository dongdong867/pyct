"""Acceptance tests for the split's list left to Python, as origin/v2 hands it back: a split
of a string the solver does not work out, and a split's list joined with another list."""

import json
from collections.abc import Callable

import pytest

from tests.acceptance.harness import input_lines, run_pyct
from tests.acceptance.test_follow_the_length_of_a_split import LENGTHS, SPLIT, covers, line_of
from tests.acceptance.test_lists import UNTIL_NO_GAIN, args_of, listed, solved

# a split's two pieces, as a list display
PIECES = ["[,]", ["[]", SPLIT, 0], ["[]", SPLIT, 1]]


# follow-the-length-of-a-split-leaves-a-split-of-an-unworked-string-to-python: a list's item,
# whose value the solver does not hold, split and read at either end, as on origin/v2
@pytest.mark.parametrize(
    ("target", "seed", "line", "agrees"),
    [
        (
            "of_a_list_s_item",
            '{"xs": ["a,b"], "n": 1}',
            'if parts[0] == "stop":',
            lambda xs, n: not len(xs[0].split(",")) < n and xs[0].split(",")[0] == "stop",
        ),
        (
            "last_line_of_a_list_s_item",
            '{"xs": ["a\\nb"]}',
            'if lines[-1] == "stop":',
            lambda xs: xs[0].splitlines()[-1] == "stop",
        ),
    ],
    ids=["a piece from the start", "the last line"],
)
def test_leaves_a_split_of_a_list_s_item_to_python(
    target: str, seed: str, line: str, agrees: Callable[..., bool]
) -> None:
    result = run_pyct(f"{LENGTHS}::{target}", seed, *UNTIL_NO_GAIN)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    at = line_of(line)
    # the split's list is Python's own: no fork reads its count
    assert all("['len', ['split" not in str(fork[1]) for fork in listed(lines[0])), lines[0]
    covered = [each for each in solved(lines) if covers(each, at + 1) and agrees(**args_of(each))]
    assert covered, lines


# follow-the-length-of-a-split-leaves-a-split-changed-at-a-position-to-python: a split's list
# joined with another tracked list is that list joined with a display of the pieces, as
# origin/v2's plain list of pieces makes it, in either order
@pytest.mark.parametrize(
    ("target", "line", "fork"),
    [
        ("joined_after", "if len(parts) == 4:", ["==", ["len", ["+", PIECES, "xs"]], 4]),
        ("joined_before", "if len(parts) > 3:", [">", ["len", ["+", "xs", PIECES]], 3]),
    ],
    ids=["the split first", "the other list first"],
)
def test_joins_a_split_with_another_list_as_python_does(
    target: str, line: str, fork: list[object]
) -> None:
    result = run_pyct(f"{LENGTHS}::{target}", '{"s": "a,b", "xs": ["x"]}', *UNTIL_NO_GAIN)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    at = line_of(line)
    assert [expression for _, expression, _ in listed(lines[0])] == [fork], lines[0]
    reached = [args_of(each) for each in solved(lines) if covers(each, at + 1)]
    assert reached, lines
    for args in reached:
        s, xs = args["s"], args["xs"]
        assert isinstance(s, str) and isinstance(xs, list), args
        assert len(s.split(",") + xs) > 3, args


# follow-the-length-of-a-split-searches-a-split-as-python-does: `in` over a split's list compares
# piece after piece, as origin/v2's plain list of pieces does, with no fork on how many pieces
# there are, so the forks after it leave the solver time to flip the search
@pytest.mark.serial
def test_searches_a_split_as_python_does() -> None:
    seed = json.dumps({"s": "\n".join(["a"] * 20)})

    result = run_pyct(f"{LENGTHS}::found_beside_a_loop", seed, "--budget", "35", timeout=60)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    searched, found = line_of('found = "END" in lines'), line_of("if found:")
    piece = lambda at: ["[]", ["splitlines", "s"], at]  # noqa: E731
    at_search = [fork for fork in listed(lines[0]) if fork[0] == searched]
    assert at_search == [(searched, ["==", piece(at), "'END'"], False) for at in range(20)]
    reached = [args_of(each) for each in solved(lines) if covers(each, found + 1)]
    assert any("END" in str(args["s"]).splitlines() for args in reached), lines


# follow-the-length-of-a-split-walks-a-split-as-python-does: a `map` over a split's list walks
# it as Python does, as the target's own loop does, so no fork reads how many pieces there are
def test_maps_a_split_as_python_does() -> None:
    result = run_pyct(f"{LENGTHS}::mapped_pieces", '{"s": "1,2"}', *UNTIL_NO_GAIN)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    mapped = line_of('numbers = list(map(int, s.split(",")))')
    at_map = [fork[1] for fork in listed(lines[0]) if fork[0] == mapped]
    assert at_map == [["isint", ["[]", SPLIT, at]] for at in range(2)], lines[0]
    reached = [args_of(each) for each in solved(lines) if covers(each, line_of('return "seven"'))]
    assert any(int(str(args["s"]).split(",")[0]) == 7 for args in reached), lines

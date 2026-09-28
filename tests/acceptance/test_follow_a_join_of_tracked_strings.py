"""Acceptance tests for follow-a-join-of-tracked-strings.

Each test spawns ``python -P -m pyct`` through the harness: a join is followed only if the fork
built on its text reaches the solver and the solver's answer runs down the side it was aimed at,
so only a real run through the command line proves it.
"""

from collections.abc import Callable
from typing import Any

import pytest

from tests.acceptance.harness import REPO_ROOT, first_line, input_lines, run_pyct
from tests.acceptance.test_lists import (
    UNTIL_NO_GAIN,
    args_of,
    downgrade_names,
    failure_detail,
    fork_line,
    listed,
    solved,
)

JOINS = "targets.strs.joins"
JOINS_FILE = str(REPO_ROOT / "targets" / "strs" / "joins.py")
# what plain Python is given for the two joins that raise, typed as the seeds that run them
NOT_ONLY_STRS: Any = ["a", 1]
NOT_ITERABLE: Any = 5


def line_of(text: str) -> int:
    """The line of the fixture that holds ``text``, counted from 1."""
    lines = (REPO_ROOT / "targets" / "strs" / "joins.py").read_text().splitlines()
    return next(number for number, line in enumerate(lines, 1) if text in line)


def heads_in(expression: object) -> set[object]:
    """Every head an expression holds, at any depth."""
    heads: set[object] = set()
    stack = [expression]
    while stack:
        part = stack.pop()
        if isinstance(part, list) and part:
            heads.add(part[0])
            stack.extend(part[1:])
    return heads


def joins_of(line: dict[str, object]) -> list[tuple[object, object, object]]:
    """The forks of a line whose expression holds a join."""
    return [fork for fork in listed(line) if "join" in heads_in(fork[1])]


def flipped_by_python(
    lines: list[dict[str, object]], expression: object, agrees: Callable[..., bool]
) -> list[dict[str, object]]:
    """The solver's lines that take ``expression``'s true side, left no plan, and whose
    arguments plain Python takes down that side too."""
    return [
        line
        for line in solved(lines)
        if any(fork[1] == expression and fork[2] for fork in listed(line))
        and line["mismatch_at"] is None
        and agrees(**args_of(line))
    ]


def raised_by_python(call: Callable[[], object]) -> str:
    """What plain Python raises for ``call`` in this run, as pyct reports a raise."""
    try:
        call()
    except TypeError as error:
        return f"TypeError: {error}"
    raise AssertionError("the call raised nothing")


# follow-a-join-of-tracked-strings-follows-a-join-of-a-list-argument
def test_follows_a_join_of_a_list_argument() -> None:
    result = run_pyct(f"{JOINS}::of_a_list", '{"parts": ["x", "y"]}', *UNTIL_NO_GAIN)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    at = line_of('"-".join(parts) == "a-b"')
    compare = ["==", ["join", "'-'", "parts"], "'a-b'"]
    assert listed(lines[0]) == [
        (at, [">", ["len", "parts"], 0], True),
        (at, [">", ["len", "parts"], 1], True),
        (at, [">", ["len", "parts"], 2], False),
        (at, compare, False),
    ]
    assert fork_line(result.stderr, JOINS_FILE, at, "'-'.join(parts) == 'a-b'", False)
    assert flipped_by_python(lines, compare, lambda parts: "-".join(parts) == "a-b"), lines
    assert all(downgrade_names(line) == [] for line in lines), lines


# follow-a-join-of-tracked-strings-follows-a-tracked-separator
def test_follows_a_tracked_separator() -> None:
    result = run_pyct(f"{JOINS}::by_a_separator", '{"sep": "-"}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    at = line_of('sep.join(["a", "b"]) == "a+b"')
    compare = ["==", ["join", "sep", ["[,]", "'a'", "'b'"]], "'a+b'"]
    assert listed(lines[0]) == [(at, compare, False)]
    assert downgrade_names(lines[0]) == []
    assert fork_line(result.stderr, JOINS_FILE, at, "sep.join(['a', 'b']) == 'a+b'", False)
    assert flipped_by_python(lines, compare, lambda sep: sep == "+"), lines


# follow-a-join-of-tracked-strings-follows-a-literal-bound-separator
def test_follows_a_literal_bound_separator() -> None:
    result = run_pyct(f"{JOINS}::by_a_bound_separator", '{"parts": ["x", "y"]}', *UNTIL_NO_GAIN)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    compare = ["==", ["join", "'-'", "parts"], "'a-b'"]
    assert (line_of("SEP.join(parts)"), compare, False) in listed(lines[0])
    assert flipped_by_python(lines, compare, lambda parts: "-".join(parts) == "a-b"), lines


# follow-a-join-of-tracked-strings-follows-a-list-the-target-builds
def test_follows_a_list_the_target_builds() -> None:
    result = run_pyct(f"{JOINS}::of_a_built_list", '{"a": "p", "b": "q"}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    at = line_of('"-".join([a, b.upper()])')
    compare = ["==", ["join", "'-'", ["[,]", "a", ["upper", "b"]]], "'x-Y'"]
    assert listed(lines[0]) == [(at, compare, False)]
    assert fork_line(result.stderr, JOINS_FILE, at, "'-'.join([a, b.upper()]) == 'x-Y'", False)
    agrees = flipped_by_python(lines, compare, lambda a, b: "-".join([a, b.upper()]) == "x-Y")
    assert agrees, lines


# follow-a-join-of-tracked-strings-follows-a-join-of-split-pieces
def test_follows_a_join_of_split_pieces() -> None:
    result = run_pyct(f"{JOINS}::of_split_pieces", '{"s": "x,y"}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    at = line_of('"-".join(s.split(",")) == "a-b"')
    split = ["split", "s", "','"]
    pieces = ["[,]", ["[]", split, 0], ["[]", split, 1]]
    compare = ["==", ["join", "'-'", pieces], "'a-b'"]
    assert listed(lines[0]) == [(at, compare, False)]
    printed = "'-'.join([s.split(',')[0], s.split(',')[1]]) == 'a-b'"
    assert fork_line(result.stderr, JOINS_FILE, at, printed, False)
    assert flipped_by_python(lines, compare, lambda s: "-".join(s.split(",")) == "a-b"), lines


# follow-a-join-of-tracked-strings-keeps-the-number-of-split-pieces
def test_keeps_the_number_of_split_pieces() -> None:
    result = run_pyct(f"{JOINS}::of_three_split_pieces", '{"s": "x,y"}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    answers = solved(lines)
    assert answers, lines
    assert all(str(args_of(line)["s"]).count(",") == 1 for line in answers), answers
    split = ["split", "s", "','"]
    pieces = ["[,]", ["[]", split, 0], ["[]", split, 1]]
    compare = ["==", ["join", "'-'", pieces], "'a-b-c'"]
    agrees = flipped_by_python(lines, compare, lambda s: "-".join(s.split(",")) == "a-b-c")
    assert agrees, lines
    assert all(line["mismatch_at"] is None for line in answers), answers


# follow-a-join-of-tracked-strings-reaches-a-join-from-an-empty-list
def test_reaches_a_join_from_an_empty_list() -> None:
    result = run_pyct(f"{JOINS}::of_a_list", '{"parts": []}', *UNTIL_NO_GAIN)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    at = line_of('"-".join(parts) == "a-b"')
    compare = ["==", ["join", "'-'", "parts"], "'a-b'"]
    assert listed(lines[0]) == [
        (at, [">", ["len", "parts"], 0], False),
        (at, compare, False),
    ]
    assert flipped_by_python(lines, compare, lambda parts: "-".join(parts) == "a-b"), lines


# follow-a-join-of-tracked-strings-follows-a-join-of-a-generator
def test_follows_a_join_of_a_generator() -> None:
    result = run_pyct(f"{JOINS}::of_a_generator", '{"parts": ["x"]}', *UNTIL_NO_GAIN)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    compare = ["==", ["join", "''", ["[,]", ["upper", ["[]", "parts", 0]]]], "'AB'"]
    assert (line_of('"".join(p.upper()'), compare, False) in listed(lines[0])
    agrees = flipped_by_python(
        lines, compare, lambda parts: "".join(p.upper() for p in parts) == "AB"
    )
    assert agrees, lines


# follow-a-join-of-tracked-strings-names-a-separator-cvc5-cannot-hold
def test_names_a_separator_cvc5_cannot_hold() -> None:
    result = run_pyct(f"{JOINS}::by_a_separator_past_cvc5", '{"parts": ["x", "y"]}', *UNTIL_NO_GAIN)

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert "join" in downgrade_names(seed), seed
    assert joins_of(seed) == [], seed


# follow-a-join-of-tracked-strings-leaves-a-separator-read-at-run-time-to-python
def test_leaves_a_separator_read_at_run_time_to_python() -> None:
    result = run_pyct(f"{JOINS}::by_a_separator_read_at_run_time", '{"a": "q"}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert joins_of(seed) == [], seed
    assert downgrade_names(seed) == [], seed
    # plain Python joins "q-b", which is not "x-b", so the function returns "other"
    covered = seed["covered"]
    assert isinstance(covered, dict), seed
    assert line_of('return "other"  # run time') in covered[JOINS_FILE], seed
    assert line_of('return "joined"  # run time') not in covered[JOINS_FILE], seed


# follow-a-join-of-tracked-strings-raises-on-an-item-that-is-not-a-string
def test_raises_on_an_item_that_is_not_a_string() -> None:
    result = run_pyct(f"{JOINS}::of_anything", '{"parts": ["a", 1]}', *UNTIL_NO_GAIN)

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert failure_detail(seed) == raised_by_python(lambda: "-".join(NOT_ONLY_STRS)), seed
    assert downgrade_names(seed) == [], seed


# follow-a-join-of-tracked-strings-raises-on-a-separator-given-no-iterable
def test_raises_on_a_separator_given_no_iterable() -> None:
    result = run_pyct(f"{JOINS}::of_what_it_is_given", '{"sep": "-", "n": 5}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert failure_detail(seed) == raised_by_python(lambda: "-".join(NOT_ITERABLE)), seed
    assert downgrade_names(seed) == [], seed


# follow-a-join-of-tracked-strings-keeps-the-number-of-split-pieces: a join of part of a split's
# list holds nothing, so a fork the seed's own number of pieces takes is flipped as without a join
def test_a_join_of_part_of_a_split_leaves_its_number_of_pieces_free() -> None:
    result = run_pyct(f"{JOINS}::of_the_first_piece", '{"s": "q,r"}')

    assert result.returncode == 0, result.stderr
    covered = covered_lines(input_lines(result.stdout))
    assert line_of('return "ends"  # first piece') in covered, result.stdout


# follow-a-join-of-tracked-strings-keeps-the-number-of-split-pieces: a split the join reads only
# as the string of another split is not one whose pieces it joins
def test_a_join_of_a_piece_split_again_leaves_the_first_split_free() -> None:
    result = run_pyct(f"{JOINS}::of_a_piece_split_again", '{"s": "q,r"}')

    assert result.returncode == 0, result.stderr
    covered = covered_lines(input_lines(result.stdout))
    assert line_of('return "ends"  # split again') in covered, result.stdout


def covered_lines(lines: list[dict[str, object]]) -> set[int]:
    """Every line of the fixture some input covered."""
    covered: set[int] = set()
    for line in lines:
        each = line["covered"]
        assert isinstance(each, dict), line
        covered |= set(each.get(JOINS_FILE, []))
    return covered


# follow-a-join-of-tracked-strings-keeps-the-number-of-split-pieces: a join that reads a split's
# last piece, or a split of a changed string, keeps every answer on the plan
@pytest.mark.parametrize(
    ("target", "seed"),
    [
        ("of_the_tail", '{"s": "a,x,y"}'),
        ("of_a_lowered_split", '{"s": "x,y"}'),
        ("of_a_stripped_split", '{"s": "x,y"}'),
    ],
)
def test_a_join_that_reads_to_a_split_s_end_leaves_no_plan(target: str, seed: str) -> None:
    result = run_pyct(f"{JOINS}::{target}", seed)

    assert result.returncode == 0, result.stderr
    answers = solved(input_lines(result.stdout))
    assert answers, result.stdout
    assert all(line["mismatch_at"] is None for line in answers), answers


# follow-a-join-of-tracked-strings-leaves-a-separator-read-at-run-time-to-python: a name bound only
# to a str literal in its module, rebound to bytes from another, joins as Python joins
def test_a_literal_bound_separator_rebound_elsewhere_raises_as_python_does() -> None:
    result = run_pyct("targets.strs.rebinds_separator::call", '{"s": "a"}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    separator: Any = b"-"
    detail = failure_detail(seed)
    assert detail == raised_by_python(lambda: separator.join(["a", "b"])), seed


# follow-a-join-of-tracked-strings-follows-a-tracked-separator: a name bound only to a str
# literal in its module, rebound to a tracked str from another, joins as a tracked separator
def test_a_literal_bound_separator_rebound_to_a_tracked_str_is_followed() -> None:
    result = run_pyct(
        "targets.strs.rebinds_to_a_tracked_separator::check", '{"sep": "-", "a": "q"}'
    )

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    compare = ["==", ["join", "sep", ["[,]", "a", "'b'"]], "'q-b'"]
    assert compare in [fork[1] for fork in listed(lines[0])], lines[0]
    assert all(line["mismatch_at"] is None for line in solved(lines)), lines

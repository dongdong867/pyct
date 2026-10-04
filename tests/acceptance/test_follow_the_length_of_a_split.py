"""Acceptance tests for follow-the-length-of-a-split.

Each test spawns ``python -P -m pyct`` through the harness: a split's length is followed only if
the fork on it reaches the solver and the solver's answer, run by plain Python, splits into the
number of pieces the path fixes.
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from tests.acceptance.harness import REPO_ROOT, first_line, input_lines, run_pyct, summary_line
from tests.acceptance.test_lists import (
    UNTIL_NO_GAIN,
    args_of,
    downgrade_names,
    failure_detail,
    fork_line,
    listed,
    solved,
)

LENGTHS = "targets.strs.split_lengths"
LENGTHS_FILE = str(REPO_ROOT / "targets" / "strs" / "split_lengths.py")
JOINS = "targets.strs.joins"
JOINS_FILE = str(REPO_ROOT / "targets" / "strs" / "joins.py")
KEYWORD = "targets.strs.split_keyword::split_on_comma"
KEYWORD_FILE = str(REPO_ROOT / "targets" / "strs" / "split_keyword.py")
SPLIT = ["split", "s", "','"]


def line_of(text: str, file: str = LENGTHS_FILE) -> int:
    """The line of a fixture that holds ``text``, counted from 1."""
    lines = Path(file).read_text().splitlines()
    return next(number for number, line in enumerate(lines, 1) if text in line)


def covers(line: dict[str, object], number: int, file: str = LENGTHS_FILE) -> bool:
    covered = line["covered"]
    assert isinstance(covered, dict), line
    return number in covered.get(file, [])


def agreeing(
    lines: list[dict[str, object]], expression: object, agrees: Callable[..., bool]
) -> list[dict[str, object]]:
    """The solver's lines that take ``expression``'s true side, left no plan, and whose
    arguments plain Python takes down that side too."""
    return [
        line
        for line in solved(lines)
        if (any(fork[1] == expression and fork[2] for fork in listed(line)))
        and line["mismatch_at"] is None
        and agrees(**args_of(line))
    ]


def aimed_at(line: dict[str, object]) -> object:
    """The line of the fork a solver line was aimed at."""
    aim = line["aim"]
    return aim.get("line") if isinstance(aim, dict) else None


def no_plan_left(lines: list[dict[str, object]]) -> bool:
    return all(line["mismatch_at"] is None for line in solved(lines))


# follow-the-length-of-a-split-follows-the-number-of-pieces
def test_follows_the_number_of_pieces() -> None:
    result = run_pyct(f"{LENGTHS}::counted", '{"s": "a,b"}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    at = line_of("if len(parts) != 4:")
    fork = ["!=", ["len", SPLIT], 4]
    assert (at, fork, True) in listed(lines[0]), lines[0]
    assert fork_line(result.stderr, LENGTHS_FILE, at, "len(s.split(',')) != 4", True)
    covered = [
        line
        for line in solved(lines)
        if covers(line, line_of('return "four"'))
        and str(args_of(line)["s"]).count(",") == 3
        and len(str(args_of(line)["s"]).split(",")) == 4
    ]
    assert covered, lines
    assert all(downgrade_names(line) == [] for line in lines), lines


# follow-the-length-of-a-split-keeps-the-count-on-a-deeper-flip
def test_keeps_the_count_on_a_deeper_flip() -> None:
    result = run_pyct(f"{LENGTHS}::second_empty", '{"s": "a|30|b"}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    covered = [
        line
        for line in solved(lines)
        if covers(line, line_of('return "second empty"'))
        and len(parts := str(args_of(line)["s"]).split("|")) == 3
        and parts[1] == ""
    ]
    assert covered, lines
    at = line_of('if parts[1] == "":')
    aimed = [line for line in solved(lines) if aimed_at(line) == at]
    assert aimed, lines
    assert all(line["mismatch_at"] is None for line in aimed), aimed


# follow-the-length-of-a-split-searches-the-pieces-as-a-list
def test_searches_the_pieces_as_a_list() -> None:
    result = run_pyct(f"{LENGTHS}::searched", '{"s": "a"}', *UNTIL_NO_GAIN)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    at = line_of('if "b" in s.split(","):')
    assert [fork for fork in listed(lines[0]) if fork[0] == at] == [
        (at, [">", ["len", SPLIT], 0], True),
        (at, ["==", ["[]", SPLIT, 0], "'b'"], False),
        (at, [">", ["len", SPLIT], 1], False),
    ]
    found = [
        line
        for line in solved(lines)
        if "b" in str(args_of(line)["s"]).split(",") and covers(line, line_of('return "found"'))
    ]
    assert found, lines


# follow-the-length-of-a-split-joins-a-split-by-its-walk
def test_joins_a_split_by_its_walk() -> None:
    result = run_pyct(f"{JOINS}::of_split_pieces", '{"s": "x,y"}', *UNTIL_NO_GAIN)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    at = line_of('"-".join(s.split(",")) == "a-b"', JOINS_FILE)
    compare = ["==", ["join", "'-'", SPLIT], "'a-b'"]
    assert [fork for fork in listed(lines[0]) if fork[0] == at] == [
        (at, [">", ["len", SPLIT], 0], True),
        (at, [">", ["len", SPLIT], 1], True),
        (at, [">", ["len", SPLIT], 2], False),
        (at, compare, False),
    ]
    printed = "'-'.join(s.split(',')) == 'a-b'"
    assert fork_line(result.stderr, JOINS_FILE, at, printed, False)
    assert agreeing(lines, compare, lambda s: "-".join(s.split(",")) == "a-b"), lines


# follow-the-length-of-a-split-joins-another-number-of-pieces
def test_joins_another_number_of_pieces() -> None:
    result = run_pyct(f"{JOINS}::of_three_split_pieces", '{"s": "x,y"}', *UNTIL_NO_GAIN)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    compare = ["==", ["join", "'-'", SPLIT], "'a-b-c'"]
    agrees = agreeing(lines, compare, lambda s: "-".join(s.split(",")) == "a-b-c")
    assert [line for line in agrees if str(args_of(line)["s"]).count(",") == 2], lines
    assert no_plan_left(lines), lines


# follow-the-length-of-a-split-counts-from-the-end
def test_counts_from_the_end() -> None:
    result = run_pyct(f"{LENGTHS}::from_the_end", '{"s": "x,y"}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    at = line_of('if parts[-1] == "z":')
    compare = ["==", ["[]", SPLIT, -1], "'z'"]
    assert [fork for fork in listed(lines[0]) if fork[0] == at] == [
        (at, [">=", ["len", SPLIT], 1], True),
        (at, compare, False),
    ]
    assert fork_line(result.stderr, LENGTHS_FILE, at, "s.split(',')[-1] == 'z'", False)
    assert agreeing(lines, compare, lambda s: s.split(",")[-1] == "z"), lines


# follow-the-length-of-a-split-counts-every-split-form
def test_counts_every_split_form() -> None:
    # a flip that asks for words and lines together can take cvc5 most of its limit, so the run
    # ends on its budget rather than on the harness's timeout
    result = run_pyct(f"{LENGTHS}::every_form", '{"s": "a"}', "--budget", "20")

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    forms: list[tuple[object, Callable[[str], bool]]] = [
        (["==", ["len", ["split", "s"]], 3], lambda s: len(s.split()) == 3),
        (["==", ["len", ["split", "s", "','", 1]], 2], lambda s: len(s.split(",", 1)) == 2),
        (["==", ["len", ["rsplit", "s", "','", 1]], 2], lambda s: len(s.rsplit(",", 1)) == 2),
        (["==", ["len", ["splitlines", "s"]], 3], lambda s: len(s.splitlines()) == 3),
    ]
    for fork, agrees in forms:
        assert agreeing(lines, fork, agrees), (fork, lines)
    at = line_of('if len(s.split(",", 1)) > 2:')
    assert any(
        entry.startswith(f"missed {LENGTHS_FILE}:{at}:") and entry.endswith(" unsat")
        for entry in result.stderr.splitlines()
    ), result.stderr
    assert no_plan_left(lines), lines


# follow-the-length-of-a-split-takes-keyword-arguments
def test_takes_keyword_arguments() -> None:
    result = run_pyct(KEYWORD, '{"s": "a,b"}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    fork = ["==", ["len", SPLIT], 2]
    assert fork in [entry[1] for entry in listed(lines[0]) if entry[2]], lines[0]
    assert downgrade_names(lines[0]) == [], lines[0]
    other = [
        line
        for line in solved(lines)
        if covers(line, 5, KEYWORD_FILE) and str(args_of(line)["s"]).split(sep=",") != ["a", "b"]
    ]
    assert other, lines


# follow-the-length-of-a-split-follows-a-change-to-the-pieces
def test_follows_a_change_to_the_pieces() -> None:
    result = run_pyct(f"{LENGTHS}::appended", '{"s": "a"}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    at = line_of("if len(parts) == 3:")
    fork = ["==", ["len", ["+", SPLIT, ["[,]", "'z'"]]], 3]
    assert (at, fork, False) in listed(lines[0]), lines[0]
    assert fork_line(result.stderr, LENGTHS_FILE, at, "len(s.split(',') + ['z']) == 3", False)
    agrees = agreeing(lines, fork, lambda s: len([*s.split(","), "z"]) == 3)
    assert [line for line in agrees if str(args_of(line)["s"]).count(",") == 1], lines


# follow-the-length-of-a-split-frees-a-join-of-the-first-pieces
def test_frees_a_join_of_the_first_pieces() -> None:
    result = run_pyct(f"{LENGTHS}::first_two_joined", '{"v": "3.12"}', *UNTIL_NO_GAIN)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    both = [
        line
        for line in lines
        if covers(line, line_of('return "patch one"'))
        and ".".join(str(args_of(line)["v"]).split(".")[:2]) == "3.12"
        and str(args_of(line)["v"]).endswith(".1")
    ]
    assert both, lines
    assert no_plan_left(lines), lines


# follow-the-length-of-a-split-reports-an-index-past-the-pieces
def test_reports_an_index_past_the_pieces() -> None:
    result = run_pyct(f"{LENGTHS}::past_the_pieces", '{"s": "a"}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert ([">", ["len", SPLIT], 1], False) in [entry[1:] for entry in listed(lines[0])]
    assert str(failure_detail(lines[0])).startswith("IndexError"), lines[0]
    whole = [
        line
        for line in solved(lines)
        if len(str(args_of(line)["s"]).split(",")) == 2 and failure_detail(line) is None
    ]
    assert whole, lines
    compare = ["==", ["[]", SPLIT, 1], "'b'"]
    assert agreeing(lines, compare, lambda s: s.split(",")[1] == "b"), lines


# follow-the-length-of-a-split-keeps-an-unencoded-split-plain
def test_keeps_an_unencoded_split_plain() -> None:
    result = run_pyct(f"{LENGTHS}::by_a_tracked_separator", '{"s": "a,b", "t": ","}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert "split" in downgrade_names(seed), seed
    at = line_of("if len(parts) == 2:")
    assert [fork for fork in listed(seed) if fork[0] == at] == [], seed
    assert covers(seed, line_of('return "two"')), seed


# follow-the-length-of-a-split-raises-on-an-empty-separator
def test_raises_on_an_empty_separator() -> None:
    result = run_pyct(f"{LENGTHS}::by_an_empty_separator", '{"s": "a"}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    text, separator = "a", ""
    with pytest.raises(ValueError) as plain:
        text.split(separator)
    assert failure_detail(seed) == f"ValueError: {plain.value}", seed
    assert listed(seed) == [], seed
    assert downgrade_names(seed) == [], seed


LINES = ["splitlines", "s"]


# follow-the-length-of-a-split-reads-plain-arithmetic-on-the-count
def test_reads_plain_arithmetic_on_the_count() -> None:
    result = run_pyct(f"{LENGTHS}::arithmetic", '{"s": "a"}', *UNTIL_NO_GAIN)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    compares: list[tuple[object, Callable[[str], bool]]] = [
        ([">", ["-", ["len", SPLIT], 1], 3], lambda s: len(s.split(",")) - 1 > 3),
        (["==", ["*", ["len", SPLIT], 2], 8], lambda s: len(s.split(",")) * 2 == 8),
        # Python asks the count's own `>` for `3 < len(parts)`
        ([">", ["len", SPLIT], 3], lambda s: len(s.split(",")) > 3),
    ]
    for compare, agrees in compares:
        assert agreeing(lines, compare, agrees), (compare, lines)
    first = [
        line
        for line in solved(lines)
        if covers(line, line_of('if parts[0] == "x":') + 1)
        and len(parts := str(args_of(line)["s"]).split(",")) >= 5
        and parts[0] == "x"
    ]
    assert first, lines
    assert no_plan_left(lines), lines


# follow-the-length-of-a-split-reads-the-last-line-at-the-input-s-count
def test_reads_the_last_line_at_the_input_s_count() -> None:
    result = run_pyct(f"{LENGTHS}::last_line", '{"s": "a\\nb\\nc"}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    at = line_of('if lines[-1] == "end":')
    assert [fork for fork in listed(lines[0]) if fork[0] == at] == [
        (at, [">=", ["len", LINES], 1], True),
        (at, ["==", ["[]", LINES, -1], "'end'"], False),
    ]
    three = [
        line
        for line in solved(lines)
        if covers(line, at + 1)
        and len(found := str(args_of(line)["s"]).splitlines()) == 3
        and found[-1] == "end"
    ]
    assert three, lines
    assert no_plan_left(lines), lines


# follow-the-length-of-a-split-asks-the-input-s-count-beside-a-tracked-value
def test_asks_the_input_s_count_beside_a_tracked_value() -> None:
    result = run_pyct(f"{LENGTHS}::beside_a_tracked_value", '{"s": "a\\nb\\nc", "n": 5}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    at = line_of("if len(lines) > n:")
    fork = [">", ["len", LINES], "n"]
    assert (at, fork, False) in listed(lines[0]), lines[0]
    assert fork_line(result.stderr, LENGTHS_FILE, at, "len(s.splitlines()) > n", False)
    below = [
        line
        for line in solved(lines)
        if (at, fork, True) in listed(line) and int(str(args_of(line)["n"])) < 3
    ]
    assert below, lines
    two = [
        line
        for line in solved(lines)
        if covers(line, line_of("return 2"))
        and (lambda s, n: n < 30 and len(s.splitlines()) > n and s.splitlines()[0] == "end")(
            **args_of(line)
        )
    ]
    assert two, lines
    solver = summary_line(result.stdout)["solver"]
    assert isinstance(solver, dict) and solver["unknown"] == solver["timeout"] == 0, solver


# follow-the-length-of-a-split-walks-a-split-after-the-other-forks, as the user decided in
# review round 9 (wording with PM): the target's loop over a split's list is Python's own walk
def test_a_loop_over_a_split_records_no_piece_fork() -> None:
    result = run_pyct(f"{LENGTHS}::walked_after", '{"s": "a\\nb\\nc\\nd"}', *UNTIL_NO_GAIN)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    walk, test = line_of("for i, p in enumerate"), line_of('if i > 0 and p == "end":')
    # no "is there another piece" fork at the loop, as on origin/v2: only the lines' own forks
    assert [fork for fork in listed(lines[0]) if fork[0] == walk] == [], lines[0]
    tests = [fork[1] for fork in listed(lines[0]) if fork[0] == test]
    assert [part[0] for part in tests if isinstance(part, list)] == ["=="] * 3, lines[0]
    assert [line for line in solved(lines) if covers(line, test + 1)], lines

"""Acceptance tests for the record-decided-checks-on-a-split-s-pieces story.

A split's list starts with a length range from the call that made it: at least one piece for a
split by a separator, at most k + 1 for a plain limit k. The forks on its length narrow the
range, a compare of `len(parts)` with a plain int among them, and a check the range proves is a
fact, not a fork. Each test runs pyct through the command line, as a person or sweep reads it.
"""

from collections.abc import Callable

import pytest

from tests.acceptance.harness import (
    REPO_ROOT,
    first_line,
    input_lines,
    lines_expressions_and_sides,
    run_pyct,
    summary_line,
)
from tests.acceptance.test_bools import at
from tests.acceptance.test_lists import failure_detail
from tests.acceptance.test_pass_keywords_through_a_downgrade import covered_in
from tests.acceptance.test_read_a_tracked_value_s_type_as_its_base_type import line_of
from tests.acceptance.test_record_a_decided_check_as_a_fact import (
    args_of,
    covered,
    missed,
    solver_lines,
)
from tests.acceptance.test_record_decided_checks_on_lists_strings_and_second_walks import unsat

RANGES = "targets.strs.split_ranges"
RANGES_FILE = REPO_ROOT / "targets" / "strs" / "split_ranges.py"
LENGTHS = "targets.strs.split_lengths"
LENGTHS_FILE = REPO_ROOT / "targets" / "strs" / "split_lengths.py"
SPLIT = ["split", "s", "','"]
COUNT = ["len", SPLIT]


def takes(line: dict[str, object], number: int, expression: object, taken: bool) -> bool:
    """Whether a printed line lists one fork at one line of the target, on one side."""
    return (number, expression, taken) in lines_expressions_and_sides(line)


def covering(stdout: str, number: int, file: str = str(RANGES_FILE)) -> list[dict[str, object]]:
    """The solver's lines that cover one line of the target."""
    return [line for line in solver_lines(stdout) if number in covered_in(line, file)]


def split_of(line: dict[str, object], name: str = "s", separator: str = ",") -> list[str]:
    """What plain Python's split makes of a printed line's argument."""
    text = args_of(line)[name]
    assert isinstance(text, str), line
    return text.split(separator)


def ranges_line(text: str, function: str) -> int:
    return line_of(RANGES_FILE, text, function)


# record-decided-checks-on-a-split-s-pieces-tests-a-separator-split-as-decided
@pytest.mark.parametrize("where", [(), ("--in-process",)], ids=["own-process", "in-process"])
def test_tests_a_separator_split_as_decided(where: tuple[str, ...]) -> None:
    result = run_pyct(f"{RANGES}::truth", '{"s": "a,b"}', *where)

    assert result.returncode == 0, result.stderr
    tested = ranges_line("if parts:", "truth")
    compared = ranges_line('if parts[0] == "end":', "truth")
    for line in input_lines(result.stdout):
        assert at(line, tested) == [], line
        assert [">", COUNT, 0] not in at(line, compared), line
    piece = ["==", ["[]", SPLIT, 0], "'end'"]
    assert takes(first_line(result.stdout), compared, piece, False)
    assert covering(result.stdout, ranges_line("return 2", "truth"))
    assert unsat(result.stderr) == []
    assert summary_line(result.stdout)["stopped"] == "no fork to flip"


# record-decided-checks-on-a-split-s-pieces-decides-a-count-the-path-compared
def test_decides_a_count_the_path_compared() -> None:
    result = run_pyct(f"{RANGES}::counted_again", '{"s": "a,b"}', "--budget", "5")

    assert result.returncode == 0, result.stderr
    counted = ranges_line("if len(parts) == 4:", "counted_again")
    again = ranges_line("if len(parts) > 2:", "counted_again")
    compared = ranges_line('if parts[3] == "end":', "counted_again")
    four = [
        line for line in input_lines(result.stdout) if takes(line, counted, ["==", COUNT, 4], True)
    ]
    assert four, result.stdout
    for line in four:
        assert at(line, again) == [], line
        assert [">", COUNT, 3] not in at(line, compared), line
    assert any(len(split_of(line)) == 4 for line in four), four
    ends = covering(result.stdout, ranges_line("return 2", "counted_again"))
    assert any(len(parts := split_of(line)) == 4 and parts[3] == "end" for line in ends), ends
    assert unsat(result.stderr) == []


# record-decided-checks-on-a-split-s-pieces-decides-a-join-after-the-count
def test_decides_a_join_after_the_count() -> None:
    result = run_pyct(f"{RANGES}::joined_after_the_count", '{"s": "a,b"}', "--budget", "5")

    assert result.returncode == 0, result.stderr
    function = "joined_after_the_count"
    counted = ranges_line("if len(parts) == 3:", function)
    joined = ranges_line('if "-".join(parts) == "a-b-end":', function)
    for line in input_lines(result.stdout):
        if takes(line, counted, ["==", COUNT, 3], True):
            walks = [e for e in at(line, joined) if isinstance(e, list) and COUNT in e]
            assert walks == [], line
    assert covering(result.stdout, ranges_line("return 2", function))
    assert unsat(result.stderr) == []


# record-decided-checks-on-a-split-s-pieces-decides-plain-arithmetic-on-the-count
def test_decides_plain_arithmetic_on_the_count() -> None:
    result = run_pyct(f"{LENGTHS}::arithmetic", '{"s": "a"}')

    assert result.returncode == 0, result.stderr
    lowered = line_of(LENGTHS_FILE, "if len(parts) - 1 > 3:", "arithmetic")
    first = line_of(LENGTHS_FILE, 'if parts[0] == "x":', "arithmetic")
    doubled = line_of(LENGTHS_FILE, "if len(parts) * 2 == 8:", "arithmetic")
    turned = line_of(LENGTHS_FILE, "if 3 < len(parts):", "arithmetic")
    for line in input_lines(result.stdout):
        if takes(line, lowered, [">", ["-", COUNT, 1], 3], True):
            assert at(line, doubled) == [] and at(line, turned) == [], line
        assert [">", COUNT, 0] not in at(line, first), line
    assert unsat(result.stderr) == []
    function_lines = set(range(lowered - 1, turned + 3))
    assert covered(result.stdout, str(LENGTHS_FILE)) >= function_lines


# record-decided-checks-on-a-split-s-pieces-caps-a-limited-split
def test_caps_a_limited_split() -> None:
    every = run_pyct(f"{LENGTHS}::every_form", '{"s": "a"}')
    right = run_pyct(f"{RANGES}::limited_from_the_right", '{"s": "a,b"}')

    assert every.returncode == 0, every.stderr
    assert right.returncode == 0, right.stderr
    never = line_of(LENGTHS_FILE, 'if len(s.split(",", 1)) > 2:', "every_form")
    for line in input_lines(every.stdout):
        assert at(line, never) == [], line
    assert not [line for line in missed(every.stderr) if f":{never}:" in line]
    start = line_of(LENGTHS_FILE, "def every_form(s):")
    # every line but the one the `> 2` check guards, which no string reaches
    reached = set(range(start + 1, never + 1)) | {line_of(LENGTHS_FILE, "return found")}
    assert covered(every.stdout, str(LENGTHS_FILE)) >= reached
    function = "limited_from_the_right"
    capped = ranges_line("if len(parts) <= 3:", function)
    for line in input_lines(right.stdout):
        assert at(line, capped) == [], line
    assert covering(right.stdout, ranges_line("return 2", function))
    assert covered(right.stdout, str(RANGES_FILE)) >= set(range(capped - 1, capped + 4))


# record-decided-checks-on-a-split-s-pieces-counts-a-list-made-from-a-split
def test_counts_a_list_made_from_a_split() -> None:
    appended = run_pyct(f"{RANGES}::appended_display", '{"s": "a,b"}')
    joined = run_pyct(f"{LENGTHS}::first_two_joined", '{"v": "3.12"}')

    assert appended.returncode == 0, appended.stderr
    assert joined.returncode == 0, joined.stderr
    longer = ranges_line("if len(parts) > 1:", "appended_display")
    for line in input_lines(appended.stdout):
        assert at(line, longer) == [], line
    assert missed(appended.stderr) == []
    assert covered(appended.stdout, str(RANGES_FILE)) >= {longer - 1, longer, longer + 1}
    cut = [">", ["len", ["[:]", ["split", "v", "'.'"], None, 2]], 0]
    for line in input_lines(joined.stdout):
        assert all(expression != cut for _, expression, _ in lines_expressions_and_sides(line))
    start = line_of(LENGTHS_FILE, "def first_two_joined(v):")
    assert covered(joined.stdout, str(LENGTHS_FILE)) >= set(range(start + 1, start + 6))


# the splits that may hand back no piece at all, each with plain Python's own
UNBOUNDED: dict[str, tuple[list[object], Callable[[str], list[str]]]] = {
    "words": (["split", "s"], str.split),
    "lines": (["splitlines", "s"], str.splitlines),
}


# record-decided-checks-on-a-split-s-pieces-keeps-whitespace-and-line-checks-forks
@pytest.mark.parametrize("function", list(UNBOUNDED))
def test_keeps_whitespace_and_line_checks_forks(function: str) -> None:
    result = run_pyct(f"{RANGES}::{function}", '{"s": "a b"}')

    assert result.returncode == 0, result.stderr
    form, python = UNBOUNDED[function]
    tested = ranges_line("if parts:", function)
    fork = ["!=", ["len", form], 0]
    assert takes(first_line(result.stdout), tested, fork, True)
    empty = [
        line
        for line in solver_lines(result.stdout)
        if takes(line, tested, fork, False) and python(str(args_of(line)["s"])) == []
    ]
    assert empty, result.stdout


# record-decided-checks-on-a-split-s-pieces-keeps-a-tracked-count-compare-a-fork
def test_keeps_a_tracked_count_compare_a_fork() -> None:
    result = run_pyct(f"{RANGES}::against_a_tracked_count", '{"s": "a,b", "n": 0}')

    assert result.returncode == 0, result.stderr
    function = "against_a_tracked_count"
    counted = ranges_line("if len(parts) == n:", function)
    longer = ranges_line("if len(parts) > 2:", function)
    lines = input_lines(result.stdout)
    # every input lists the compare at C as the base does, and some input takes each side
    for line in lines:
        assert at(line, counted) == [["==", COUNT, "n"]], line
    assert takes(lines[0], counted, ["==", COUNT, "n"], False)
    assert any(takes(line, counted, ["==", COUNT, "n"], True) for line in lines), lines
    reached = [line for line in lines if longer in covered_in(line, str(RANGES_FILE))]
    assert reached, lines
    for line in reached:
        assert at(line, longer) == [[">", COUNT, 2]], line


# record-decided-checks-on-a-split-s-pieces-walks-a-split-with-no-piece-fork
def test_walks_a_split_with_no_piece_fork() -> None:
    result = run_pyct(f"{RANGES}::walked", '{"s": "a,b"}')

    assert result.returncode == 0, result.stderr
    walked = ranges_line("for p in parts:", "walked")
    tested = ranges_line("if parts:", "walked")
    longer = ranges_line("if len(parts) > 0:", "walked")
    searched = ranges_line('if "b" in parts:', "walked")
    for line in input_lines(result.stdout):
        assert at(line, walked) == at(line, tested) == at(line, longer) == [], line
    pieces = [["==", ["[]", SPLIT, 0], "'b'"], ["==", ["[]", SPLIT, 1], "'b'"]]
    assert at(first_line(result.stdout), searched) == pieces
    assert unsat(result.stderr) == []


# record-decided-checks-on-a-split-s-pieces-decides-an-index-past-a-limited-split
def test_decides_an_index_past_a_limited_split() -> None:
    result = run_pyct(f"{RANGES}::past_a_limit", '{"s": "a,b,c"}', "--budget", "5")

    assert result.returncode == 0, result.stderr
    indexed = ranges_line('if parts[2] == "x":', "past_a_limit")
    for line in input_lines(result.stdout):
        assert str(failure_detail(line)).startswith("IndexError"), line
        assert at(line, indexed) == [], line
    assert unsat(result.stderr) == []
    assert summary_line(result.stdout)["stopped"] == "no fork to flip"

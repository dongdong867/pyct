"""Acceptance tests for the follow-character-checks-case-and-split child of the follow-strings
story.

Each test spawns ``python -P -m pyct`` through the harness, as the other string tests do: a
check, a case change or a split is followed only if the fork built on it reaches the solver
and the solver's answer runs, so only a real run through the command line proves it.
"""

import time
from pathlib import Path

from tests.acceptance.harness import (
    REPO_ROOT,
    first_line,
    hanging_cvc5,
    input_lines,
    run_pyct,
    summary_line,
)
from tests.acceptance.test_let_cvc5_answer_unknown_at_its_time_limit import misses_of
from tests.acceptance.test_str_pieces import answered_every_fork, sides_of
from tests.acceptance.test_strs import forks_of, text

CHECKS = "targets.strs.checks::classify"
CHECK_NAMES = [
    "isdigit",
    "isdecimal",
    "isnumeric",
    "isalpha",
    "isalnum",
    "isspace",
    "isupper",
    "islower",
    "isascii",
    "isprintable",
    "istitle",
    "isidentifier",
]
CASES = "targets.strs.cases::shape"
# each fork the seed takes in ``shape``, in order: the line and the expression
CASES_FORKS: list[tuple[int, list[object]]] = [
    (2, ["==", ["upper", "s"], "'AB'"]),
    (4, ["==", ["lower", "s"], "'cd'"]),
    (6, ["==", ["capitalize", "s"], "'Ef'"]),
    (8, ["==", ["title", "s"], "'Gh Ij'"]),
    (10, ["==", ["swapcase", "s"], "'kL'"]),
    (12, ["==", ["casefold", "s"], "'mn'"]),
    (14, ["==", ["strip", "s"], "'op'"]),
    (16, ["==", ["lstrip", "s", "'-'"], "'qr'"]),
    (18, ["==", ["rstrip", "s"], "'st'"]),
    (20, ["==", ["zfill", "s", 3], "'007'"]),
    (22, ["==", ["center", "s", 5, "'*'"], "'*uv**'"]),
    (24, ["==", ["ljust", "s", 3, "'.'"], "'w..'"]),
    (26, ["==", ["rjust", "s", 4], "'  yz'"]),
]
LOWER_OR_UPPER = "targets.strs.lower_or_upper::case"
PAST_ASCII_UPPER = "targets.strs.past_ascii_upper::shout"
PAST_ASCII_LOWER = "targets.strs.past_ascii_lower::shout"
REQUEST_LINE = "targets.strs.request_line::method"
REQUEST_LINE_FILE = str(REPO_ROOT / "targets" / "strs" / "request_line.py")
SPLIT_FAMILY = "targets.strs.split_family::route"
# each fork the seed takes in ``route``, in order: the line and the expression
SPLIT_FAMILY_FORKS: list[tuple[int, list[object]]] = [
    (2, ["==", ["[]", ["split", "s"], 0], "'GET'"]),
    (4, ["==", ["[]", ["split", "s", "','", 1], 1], "'b,c'"]),
    (6, ["==", ["[]", ["rsplit", "s", "'/'", 1], 0], "'x/y'"]),
    (8, ["==", ["[]", ["partition", "s", "'='"], 2], "'on'"]),
    (10, ["==", ["[]", ["splitlines", "s"], 0], "'top'"]),
]
TRACKED_RSPLIT = "targets.strs.tracked_rsplit::cut"
LONG_RSPLIT = "targets.strs.long_rsplit::head"
LONG_RSPLIT_FILE = str(REPO_ROOT / "targets" / "strs" / "long_rsplit.py")
SHOUTED_PAIR = "targets.strs.shouted_pair::pair"
SHOUTED_PAIR_FILE = str(REPO_ROOT / "targets" / "strs" / "shouted_pair.py")


def aimed_lines_reached(inputs: list[dict[str, object]]) -> bool:
    """Whether every input the solver handed back took the side it was aimed at."""
    return all(line["mismatch_at"] is None for line in inputs[1:])


def _head(fork: dict[str, object]) -> str:
    """The operation a fork's expression leads with."""
    expression = fork["expression"]
    assert isinstance(expression, list), fork
    return str(expression[0])


# follow-strings-follows-character-checks
def test_follows_character_checks() -> None:
    result = run_pyct(CHECKS, '{"s": ""}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    passed = {
        _head(fork): text(line, "s") for line in inputs for fork in forks_of(line) if fork["taken"]
    }
    # every check is passed by some input, and Python agrees that input passes it
    assert sorted(passed) == sorted(CHECK_NAMES)
    assert all(getattr(s, check)() for check, s in passed.items()), passed
    assert aimed_lines_reached(inputs)
    assert summary_line(result.stdout)["stopped"] == "no fork to flip"


# follow-strings-follows-case-and-padding
def test_follows_case_and_padding() -> None:
    result = run_pyct(CASES, '{"s": "x"}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    assert [(fork["line"], fork["expression"]) for fork in forks_of(inputs[0])] == CASES_FORKS
    # every fork is flipped: some input takes each side of each, and Python agrees with each
    assert sides_of(inputs) == {
        (line, repr(expression), taken)
        for line, expression in CASES_FORKS
        for taken in (True, False)
    }
    assert aimed_lines_reached(inputs)
    assert answered_every_fork(result.stdout)
    assert summary_line(result.stdout)["stopped"] == "no fork to flip"


# follow-strings-follows-islower-as-python-does
def test_follows_islower_as_python_does() -> None:
    result = run_pyct(LOWER_OR_UPPER, '{"s": "123"}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    # "123" has no cased character, so it is neither lower nor upper, and each flips
    taken = {(fork["line"], fork["taken"]) for line in inputs for fork in forks_of(line)}
    assert {(2, True), (4, True)} <= taken
    solver = summary_line(result.stdout)["solver"]
    assert isinstance(solver, dict) and solver["unsat"] == 0, solver
    assert not [line for line in result.stderr.splitlines() if line.endswith(" unsat")]
    # a digit beside lowercase letters leaves s lowercase, as Python says
    seed = first_line(run_pyct(LOWER_OR_UPPER, '{"s": "abc1"}').stdout)
    assert forks_of(seed)[0]["expression"] == ["islower", "s"]
    assert forks_of(seed)[0]["taken"] is True


def _reported_taken(stdout: str) -> list[str]:
    """Each input whose line reports the fork taken, by its s."""
    return [
        text(line, "s")
        for line in input_lines(stdout)
        if any(fork["taken"] for fork in forks_of(line))
    ]


# follow-strings-keeps-a-non-ascii-approximation-honest
def test_keeps_a_non_ascii_approximation_honest() -> None:
    result = run_pyct(PAST_ASCII_LOWER, '{"s": "x"}')

    assert result.returncode == 0, result.stderr
    # the fork is recorded, so what follows is the solver's doing, not a lost condition
    seed, *solved = input_lines(result.stdout)
    assert [(fork["expression"], fork["taken"]) for fork in forks_of(seed)] == [
        (["==", ["upper", "s"], "'é'"], False)
    ]
    # no str's upper() is "é"; cvc5's leaves é as it is, so the solver's é leaves the plan
    left = bool(solved) and all(line["mismatch_at"] is not None for line in solved)
    assert misses_of(result.stdout) or left, result.stdout
    assert _reported_taken(result.stdout) == []


# beside follow-strings-keeps-a-non-ascii-approximation-honest, not a criterion of its own: a
# fork past ASCII that Python does take is reported taken, and only there
def test_reports_a_non_ascii_fork_taken_where_python_takes_it() -> None:
    result = run_pyct(PAST_ASCII_UPPER, '{"s": "x"}')

    assert result.returncode == 0, result.stderr
    # É is its own upper() in Python and in cvc5 alike, so the solver's É takes the fork
    taken = _reported_taken(result.stdout)
    assert taken, result.stdout
    assert all(s.upper() == "É" for s in taken)


# follow-strings-follows-split
def test_follows_split() -> None:
    result = run_pyct(REQUEST_LINE, '{"line": "POST /x"}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    expression = ["==", ["[]", ["split", "line", "' '"], 0], "'GET'"]
    assert [fork["expression"] for fork in forks_of(inputs[0])] == [expression]
    assert any(text(line, "line").startswith("GET") for line in inputs[1:]), inputs
    assert f"fork {REQUEST_LINE_FILE}:3:7  line.split(' ')[0] == 'GET'  not taken" in (
        result.stderr.splitlines()
    )


# follow-strings-follows-the-split-family
def test_follows_the_split_family() -> None:
    result = run_pyct(SPLIT_FAMILY, '{"s": "a,b"}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    assert [(fork["line"], fork["expression"]) for fork in forks_of(inputs[0])] == (
        SPLIT_FAMILY_FORKS
    )
    assert sides_of(inputs) == {
        (line, repr(expression), taken)
        for line, expression in SPLIT_FAMILY_FORKS
        for taken in (True, False)
    }
    assert aimed_lines_reached(inputs)
    # the list is Python's own, so taking a piece out of it records nothing, not even partition
    # asking a str subclass for its text
    assert all(line["downgrades"] == [] for line in inputs), inputs
    assert summary_line(result.stdout)["stopped"] == "no fork to flip"


# follow-strings-reports-a-slow-encoding-as-a-miss
def test_reports_a_slow_encoding_as_a_miss(tmp_path: Path) -> None:
    # a cvc5 that never answers stands in for one slower than the budget: the real one answers
    # this fork in about 50 ms, which no budget cuts short reliably
    hanging_cvc5(tmp_path)

    result = run_pyct(SHOUTED_PAIR, '{"s": "x y"}', "--budget", "2", path=str(tmp_path))

    assert result.returncode == 0, result.stderr
    assert (2, "timeout") in misses_of(result.stdout), result.stdout
    assert f"missed {SHOUTED_PAIR_FILE}:2:7 timeout" in result.stderr.splitlines()
    assert _reported_taken(result.stdout) == []
    assert summary_line(result.stdout)["stopped"] == "budget spent"


# follow-strings-records-an-untaught-method-as-a-downgrade, for an rsplit pyct does not encode
def test_an_rsplit_on_a_tracked_separator_adds_only_its_downgrade_to_the_line() -> None:
    result = run_pyct(TRACKED_RSPLIT, '{"s": "xabyab", "t": "aba"}')

    assert result.returncode == 0, result.stderr
    # the target made one rsplit call and no compare; pyct's own look at the separator adds
    # nothing to its line
    seed = first_line(result.stdout)
    assert seed["forks"] == []
    assert seed["downgrades"] == [{"name": "rsplit", "count": 1}]


# follow-strings-reports-a-slow-encoding-as-a-miss, for an rsplit with a limit of 2,000
def test_an_rsplit_with_a_large_limit_ends_within_the_budget() -> None:
    started = time.perf_counter()
    result = run_pyct(LONG_RSPLIT, '{"s": "b,c"}', "--budget", "3")
    elapsed = time.perf_counter() - started

    assert result.returncode == 0, result.stderr
    # render writes the 2,000 steps in a few hundredths of a second; cvc5 does not answer
    # them within the budget, and pyct stops it a second past its limit
    assert (2, "timeout") in misses_of(result.stdout), result.stdout
    assert summary_line(result.stdout)["stopped"] == "budget spent"
    assert elapsed < 3 + 1 + 2, elapsed

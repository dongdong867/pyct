"""Acceptance tests for see-why-a-line-was-missed over the paths Python compiles apart.

A guard around a `with`, a `finally`, a comprehension, an `except` or an
`await` still guards the lines Python copies into its cleanup code; a line
two paths reach names the first side no input took; a fork before an
operation that may raise is told apart from the test at the same column.
"""

import pytest

from tests.acceptance.harness import REPO_ROOT, run_pyct, summary_line


def spec(module: str, function: str) -> tuple[str, str]:
    """A target under ``targets/why``: what the command line names, and F, its file."""
    return f"targets.why.{module}::{function}", str(REPO_ROOT / "targets" / "why" / f"{module}.py")


GUARDED_FILE = spec("guarded", "")[1]
JOINS_FILE = spec("joins", "")[1]
SHARED_FILE = spec("shared_site", "")[1]


def entry_for(stdout: str, line: int) -> dict[str, object]:
    """The one cause whose lines hold ``line``."""
    entries = summary_line(stdout)["why_uncovered"]
    assert isinstance(entries, list), stdout
    holding = [entry for entry in entries if line in entry["lines"]]
    assert len(holding) == 1, entries
    return holding[0]


def not_taken(file: str, line: int, col: int, side: bool, **tries: int) -> dict[str, object]:
    """What an entry says past its lines when no input took ``side`` of the fork at the site."""
    counts = {"not_tried": 0, "unsat": 0, "unknown": 0, "timeout": 0, "left_the_plan": 0}
    return {
        "reason": "not taken",
        "condition": {"file": file, "line": line, "col": col, "side": side},
        "tries": {**counts, **tries},
    }


def cause(entry: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in entry.items() if key not in ("file", "lines")}


# the guard's line, and every line under it Python may also copy into cleanup code
GUARDED = [
    ("with_in_branch", 5, [6, 7]),
    ("comp_in_branch", 12, [13, 14]),
    ("finally_in_branch", 19, [20, 21, 23, 24]),
    ("except_in_branch", 29, [30, 31, 32, 33]),
    ("awaited", 38, [39, 40]),
]


# see-why-a-line-was-missed-blames-the-first-untaken-side-on-the-way
@pytest.mark.parametrize(("function", "guard", "lines"), GUARDED, ids=[row[0] for row in GUARDED])
def test_a_guard_around_code_python_copies_guards_every_copy(
    function: str, guard: int, lines: list[int]
) -> None:
    target, _ = spec("guarded", function)

    result = run_pyct(target, '{"x": 2}')

    assert result.returncode == 0, result.stderr
    for line in lines:
        entry = entry_for(result.stdout, line)
        assert cause(entry) == not_taken(GUARDED_FILE, guard, 7, True, unsat=1), line
        assert entry["lines"] == lines


# see-why-a-line-was-missed-names-the-first-reaching-side-no-input-took
def test_a_line_either_side_of_an_or_reaches_names_the_first_side_no_input_took() -> None:
    target, _ = spec("joins", "or_join")

    result = run_pyct(target, '{"x": 2}')

    assert result.returncode == 0, result.stderr
    assert cause(entry_for(result.stdout, 3)) == not_taken(JOINS_FILE, 2, 7, True, unsat=1)


def test_the_line_after_an_elif_chain_names_the_first_branch_no_input_took() -> None:
    target, _ = spec("joins", "elif_chain")

    result = run_pyct(target, '{"x": 2}')

    assert result.returncode == 0, result.stderr
    # line 9 and line 14 both wait on `x != x`; line 11 waits on the elif
    assert entry_for(result.stdout, 14)["lines"] == [9, 14]
    assert cause(entry_for(result.stdout, 14)) == not_taken(JOINS_FILE, 8, 7, True, unsat=1)
    assert cause(entry_for(result.stdout, 11)) == not_taken(JOINS_FILE, 10, 9, True, unsat=1)


def test_the_line_after_a_loop_names_the_loop_s_test_no_input_left_by() -> None:
    target, _ = spec("joins", "loop_forever")

    result = run_pyct(target, '{"x": 2}')

    assert result.returncode == 0, result.stderr
    assert cause(entry_for(result.stdout, 23)) == not_taken(JOINS_FILE, 18, 10, False, unsat=1)


def test_no_input_ended_so_no_line_says_ended_before() -> None:
    target, _ = spec("joins", "or_join")

    result = run_pyct(target, '{"x": 2}')

    reasons = [entry["reason"] for entry in summary_line(result.stdout)["why_uncovered"]]  # type: ignore[union-attr]
    assert "ended before" not in reasons


def test_a_test_at_the_column_of_an_index_s_fork_is_judged_by_its_own_forks() -> None:
    target, _ = spec("shared_site", "first_differs")

    result = run_pyct(target, '{"s": "ab"}')

    assert result.returncode == 0, result.stderr
    # the index's length fork at 2:7 took its true side; the compare there never did
    assert cause(entry_for(result.stdout, 3)) == not_taken(SHARED_FILE, 2, 7, True, unsat=1)


def test_a_test_at_the_column_of_a_division_s_fork_is_judged_by_its_own_forks() -> None:
    target, _ = spec("shared_site", "divided")

    result = run_pyct(target, '{"x": 1}')

    assert result.returncode == 0, result.stderr
    assert cause(entry_for(result.stdout, 9)) == not_taken(SHARED_FILE, 8, 7, True, unsat=1)


# see-why-a-line-was-missed-says-a-plain-condition-recorded-no-fork
def test_a_plain_first_operand_of_an_and_is_named_not_the_second_that_never_ran() -> None:
    target, file = spec("plain_and", "guarded")

    result = run_pyct(target, '{"x": 1}')

    assert result.returncode == 0, result.stderr
    assert cause(entry_for(result.stdout, 6)) == {
        "reason": "no fork",
        "condition": {"file": file, "line": 5, "col": 7, "side": True},
    }


# see-why-a-line-was-missed-puts-the-lines-after-a-raising-operation-on-its-fork
def test_a_division_whose_raise_is_caught_keeps_its_fork() -> None:
    target, file = spec("caught", "caught")

    result = run_pyct(target, '{"x": 2}')

    assert result.returncode == 0, result.stderr
    assert cause(entry_for(result.stdout, 4)) == not_taken(file, 3, 12, True, unsat=1)


# see-why-a-line-was-missed-names-the-side-no-input-took
def test_a_substituted_in_s_test_is_the_condition_on_the_way() -> None:
    target, file = spec("substituted_in", "never_part")

    result = run_pyct(target, '{"s": "a"}')

    assert result.returncode == 0, result.stderr
    # the call that stands in for the `in` leaves the `if`'s jump where Python put it
    assert cause(entry_for(result.stdout, 4)) == not_taken(file, 3, 7, True, unsat=1)


def test_a_walk_s_pass_fork_is_the_condition_at_its_for_line() -> None:
    target, file = spec("empty_walk", "walk_nothing")

    result = run_pyct(target, '{"s": "a"}')

    assert result.returncode == 0, result.stderr
    # the walk over s[:0] ends at once; its pass fork sits where the loop steps, at 3:13
    assert cause(entry_for(result.stdout, 4)) == not_taken(file, 3, 13, True, unsat=1)

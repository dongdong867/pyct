"""Acceptance tests for see-why-a-line-was-missed over the paths Python compiles apart.

A guard around a `with`, a `finally`, a comprehension, an `except` or an
`await` still guards the lines Python copies into its cleanup code; a line
two paths reach names the first side no input took; a fork before an
operation that may raise is told apart from the test at the same column.
"""

import json
import os
import subprocess
import time

import pytest

from pyct.config.budget import Budget
from pyct.config.limits import Limits
from pyct.results import why as why_module
from pyct.results.jsonl import render_summary
from pyct.results.trace import render_stop
from pyct.run.isolation import Isolation
from pyct.run.run import run
from pyct.run.target import load_target
from tests.acceptance.harness import (
    REPO_ROOT,
    check_every_uncovered_line_explained_once,
    let_pyct_run_in_process,
    run_pyct,
    summary_line,
)


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
    counts = {
        "not_tried": 0,
        "unsat": 0,
        "unknown": 0,
        "timeout": 0,
        "left_the_plan": 0,
        "decided": 0,
    }
    return {
        "reason": "not taken",
        "condition": {"file": file, "line": line, "col": col, "side": side},
        "tries": {**counts, **tries},
    }


def cause(entry: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in entry.items() if key not in ("file", "lines")}


# each `negated` target's input lines and stderr fork lines as c586d3ba printed them on 3.12, 3.13
# and 3.14 alike, the repository's folder written <root>. They pin the whole lines, cvc5's answers
# and each line's `total` among them, so an edit to `targets/why/negated.py` or a new cvc5 that
# answers otherwise records them again, in one process so no two workers write the file at once:
# PYCT_RECORD_PRINTED=1 uv run pytest tests/acceptance/test_see_why_a_line_was_missed_paths.py
#     -n 0 -k "negated or no_fork"
# and the diff then shows the change, which a person checks is no printed change of pyct's
NEGATED_PRINTED_FILE = REPO_ROOT / "tests" / "acceptance" / "negated_printed.json"
RECORD_PRINTED = os.environ.get("PYCT_RECORD_PRINTED") == "1"


def printed(result: subprocess.CompletedProcess[str]) -> dict[str, list[str]]:
    """A run's input lines and stderr fork lines, the repository's folder written <root>."""
    inputs = result.stdout.splitlines()[:-1]
    forks = [line for line in result.stderr.splitlines() if line.startswith("fork ")]
    root = str(REPO_ROOT)
    return {
        "inputs": [line.replace(root, "<root>") for line in inputs],
        "forks": [line.replace(root, "<root>") for line in forks],
    }


def check_printed(function: str, result: subprocess.CompletedProcess[str]) -> None:
    """That the run printed what the base did, or, while recording, keep what it printed and
    skip."""
    held = json.loads(NEGATED_PRINTED_FILE.read_text())
    if not RECORD_PRINTED:
        assert printed(result) == held[function]
        return
    assert "PYTEST_XDIST_WORKER" not in os.environ, "record the printed lines with -n 0"
    held[function] = printed(result)
    NEGATED_PRINTED_FILE.write_text(json.dumps(held, indent=1) + "\n")
    # a recording checks nothing, so it never reads as a pass
    pytest.skip("printed lines recorded; run again without PYCT_RECORD_PRINTED to check them")


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


# an `in` or `is` test whose value reads the other way from the forks pyct records there: a `not`
# pyct folds and 3.14 does not, an element search's `==` forks, and an `is` against a bool, whose
# fork is the operand's. Each is judged by the forks' side, on every release; the site, the side,
# and how many times the solver found the side unsat
NEGATED = [
    ("not_in", '{"s": "a"}', 8, (4, 11, False), 1),
    ("while_not_in", '{"s": "a"}', 16, (14, 14, False), 1),
    ("is_not_true", '{"x": 0}', 24, (22, 7, True), 1),
    ("not_in_set", '{"x": 0}', 36, (34, 11, True), 2),
    ("not_in_set_written", '{"x": 0}', 44, (42, 7, True), 2),
    ("not_in_list", '{"x": 0}', 52, (50, 11, True), 2),
    ("is_not_flag", '{"x": 0}', 67, (65, 7, True), 1),
    ("not_first_in", '{"s": "1"}', 78, (76, 11, False), 1),
    ("int_not_in", '{"s": "7"}', 88, (86, 7, True), 2),
    ("is_false_no_else", '{"x": 0}', 96, (95, 7, False), 1),
    ("while_is_not_true", '{"x": 0}', 105, (104, 10, False), 1),
    ("false_is_compare", '{"x": 0}', 121, (120, 7, False), 1),
    ("pair_one", '{"x": 0, "flag": true}', 133, (132, 7, True), 1),
    ("ifexp_is_false", '{"x": 0}', 142, (141, 7, False), 2),
    ("false_is_ifexp", '{"x": 0}', 151, (150, 7, False), 2),
]


@pytest.mark.parametrize(("function", "seed", "line", "side", "unsat"), NEGATED)
def test_a_negated_test_is_judged_by_the_side_of_the_fork_it_records(
    function: str, seed: str, line: int, side: tuple[int, int, bool], unsat: int
) -> None:
    target, file = spec("negated", function)

    result = run_pyct(target, seed)

    assert result.returncode == 0, result.stderr
    assert cause(entry_for(result.stdout, line)) == not_taken(file, *side, unsat=unsat)
    # read-an-is-test-against-a-name-per-pass-keeps-every-shape-that-reads-right
    check_printed(function, result)


# a test no fork was recorded at, read in the sense of its `is` or `in` on every release: `done is
# False` was never true, and neither was `key in TABLE` where the code says `not key in TABLE`
NO_FORK = [("plain_is_false", 58, (57, 7)), ("not_in_table", 113, (111, 11))]


@pytest.mark.parametrize(("function", "line", "site"), NO_FORK)
def test_a_test_with_no_fork_reads_in_the_sense_of_its_is_or_in(
    function: str, line: int, site: tuple[int, int]
) -> None:
    target, file = spec("negated", function)

    result = run_pyct(target, '{"x": 0}')

    assert result.returncode == 0, result.stderr
    assert cause(entry_for(result.stdout, line)) == {
        "reason": "no fork",
        "condition": {"file": file, "line": site[0], "col": site[1], "side": True},
    }
    check_printed(function, result)


def test_a_walk_s_pass_fork_is_the_condition_at_its_for_line() -> None:
    target, file = spec("empty_walk", "walk_nothing")

    result = run_pyct(target, '{"s": "a"}')

    assert result.returncode == 0, result.stderr
    # the walk over s[:0] ends at once; its pass fork sits where the loop steps, at 3:13
    assert cause(entry_for(result.stdout, 4)) == not_taken(file, 3, 13, True, unsat=1)


# see-why-a-line-was-missed-names-the-side-no-input-took
def test_two_tests_at_one_site_are_judged_by_the_side_each_took() -> None:
    target, file = spec("chained", "chained")

    result = run_pyct(target, '{"x": 0}')

    assert result.returncode == 0, result.stderr
    # `x < 5 < x` tests twice at 2:7; the first test's true side proves nothing of the second's
    assert cause(entry_for(result.stdout, 3)) == not_taken(file, 2, 7, True, unsat=1)


# see-why-a-line-was-missed-says-inputs-ended-before-a-line
def test_a_raise_the_function_caught_ends_the_input_before_the_line() -> None:
    target, file = spec("caught_in_loop", "caught_in_loop")

    result = run_pyct(target, '{"x": 0}')

    assert result.returncode == 0, result.stderr
    # `TABLE["z"]` raises on every pass and `continue` goes on: the input raised before line 9
    entry = entry_for(result.stdout, 9)
    assert entry == {"file": file, "lines": [9], "reason": "ended before"}


# see-why-a-line-was-missed-says-a-generator-was-left-suspended
def test_a_generator_its_caller_stopped_asking_is_suspended_at_its_yield() -> None:
    target, file = spec("suspended", "first")

    result = run_pyct(target, '{"x": 1}')

    assert result.returncode == 0, result.stderr
    entry = entry_for(result.stdout, 3)
    assert entry == {
        "file": file,
        "lines": [3, 4],
        "reason": "suspended",
        "yield": {"file": file, "line": 2},
    }
    why = f"why 3, 4 in {file}: suspended at the yield on {file}:2"
    assert why in result.stderr.splitlines()


# see-why-a-line-was-missed-says-inputs-ended-before-a-line
def test_a_generator_that_raised_past_its_yield_ended_before_the_line() -> None:
    target, file = spec("raised_past", "raised_past")

    result = run_pyct(target, '{"x": 1}')

    assert result.returncode == 0, result.stderr
    # the caller asked again, and `{}["k"]` raised on line 3: the generator went on past line 2
    assert entry_for(result.stdout, 4) == {"file": file, "lines": [4], "reason": "ended before"}


# see-why-a-line-was-missed-says-a-generator-was-left-suspended
@pytest.mark.parametrize(
    ("module", "function", "line", "at"),
    [("at_await", "at_await", 6, 5), ("via_yield_from", "via_yield_from", 8, 7)],
    ids=["await", "yield from"],
)
def test_a_frame_left_inside_an_await_or_a_yield_from_is_suspended_there(
    module: str, function: str, line: int, at: int
) -> None:
    target, file = spec(module, function)

    result = run_pyct(target, '{"x": 1}')

    assert result.returncode == 0, result.stderr
    assert entry_for(result.stdout, line) == {
        "file": file,
        "lines": [line],
        "reason": "suspended",
        "yield": {"file": file, "line": at},
    }


# see-why-a-line-was-missed-says-a-plain-condition-recorded-no-fork
def test_the_line_after_an_async_for_waits_on_the_loop_running_out() -> None:
    target, file = spec("async_for", "async_for")

    result = run_pyct(target, '{"x": 1}')

    assert result.returncode == 0, result.stderr
    # the loop's end is a handler in the compiled code, but it is the loop's own false side
    assert cause(entry_for(result.stdout, 12)) == {
        "reason": "no fork",
        "condition": {"file": file, "line": 10, "col": 19, "side": False},
    }


# the async and generator shapes a run leaves part way, each with the cause its lines read
SHAPES = [
    ("async_with", 13, {"reason": "not taken", "line": 12}),
    ("async_gen", 23, {"reason": "suspended", "yield": 22}),
    ("yield_in_finally", 41, {"reason": "suspended", "yield": 40}),
    ("await_in_comprehension", 59, {"reason": "not called"}),
]


# see-why-a-line-was-missed-accounts-for-every-uncovered-line-once
@pytest.mark.parametrize(("function", "line", "expected"), SHAPES, ids=[row[0] for row in SHAPES])
def test_async_and_generator_shapes_left_part_way_each_read_their_cause(
    function: str, line: int, expected: dict[str, object]
) -> None:
    target, _ = spec("async_shapes", function)

    result = run_pyct(target, '{"x": 1}')

    assert result.returncode == 0, result.stderr
    entry = entry_for(result.stdout, line)
    assert entry["reason"] == expected["reason"]
    if "line" in expected:
        assert entry["condition"]["line"] == expected["line"]  # type: ignore[index]
    if "yield" in expected:
        assert entry["yield"]["line"] == expected["yield"]  # type: ignore[index]


def test_a_generator_expression_a_caller_stops_asking_leaves_no_line_behind() -> None:
    target, _ = spec("async_shapes", "genexpr")

    result = run_pyct(target, '{"x": 1}')

    assert result.returncode == 0, result.stderr
    assert 55 not in summary_line(result.stdout)["uncovered"][spec("async_shapes", "")[1]]  # type: ignore[index]


LOOPING = [
    ("takes_one", 8, {"reason": "suspended", "yield": 7}),
    ("run_async", 35, {"reason": "suspended", "yield": 34}),
    ("resumed_raise", 19, {"reason": "ended before"}),
]


# see-why-a-line-was-missed-says-a-generator-was-left-suspended
@pytest.mark.parametrize(("function", "line", "expected"), LOOPING, ids=[row[0] for row in LOOPING])
def test_a_generator_paused_at_a_yield_in_a_loop_is_suspended_and_one_that_raised_ended(
    function: str, line: int, expected: dict[str, object]
) -> None:
    target, file = spec("looping_yield", function)

    result = run_pyct(target, '{"x": 1}')

    assert result.returncode == 0, result.stderr
    entry = entry_for(result.stdout, line)
    assert entry["reason"] == expected["reason"]
    if "yield" in expected:
        assert entry["yield"] == {"file": file, "line": expected["yield"]}


# see-why-a-line-was-missed-stops-at-the-deadline
def test_the_lines_left_when_the_deadline_comes_are_not_worked_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target, file = spec("suspended", "first")
    let_pyct_run_in_process(monkeypatch)
    # the analysis reads its clock after the run, as if the deadline plus half a second is past
    monkeypatch.setattr(why_module, "clock", lambda: time.monotonic() + 3600)
    limits = Limits(budget=Budget(seconds=60))

    result = run(load_target(target), {"x": 1}, limits=limits, isolation=Isolation.IN_PROCESS)

    summary = json.loads(render_summary(result))
    check_every_uncovered_line_explained_once(render_summary(result))
    entries = summary["why_uncovered"]
    assert entries == [
        {"file": file, "lines": summary["uncovered"][file], "reason": "not worked out"}
    ]
    assert "not worked out before the deadline" in render_stop(result)


def test_a_run_with_no_budget_works_out_every_line(monkeypatch: pytest.MonkeyPatch) -> None:
    target, _ = spec("suspended", "first")
    let_pyct_run_in_process(monkeypatch)
    monkeypatch.setattr(why_module, "clock", lambda: time.monotonic() + 3600)

    result = run(load_target(target), {"x": 1}, isolation=Isolation.IN_PROCESS)

    assert "not worked out" not in {entry.reason.value for entry in result.why_uncovered}


# see-why-a-line-was-missed-puts-the-lines-after-a-raising-operation-on-its-fork
def test_the_line_after_popping_an_empty_list_waits_on_its_not_empty_fork() -> None:
    target, file = spec("pop_empty", "pop_empty")

    result = run_pyct(target, '{"items": []}')

    assert result.returncode == 0, result.stderr
    # pop checks the list is not empty before Python may raise, as pop(0) and items[0] do; past
    # `if items:` the list is empty, so that check is never true
    assert cause(entry_for(result.stdout, 5)) == not_taken(file, 4, 8, True, unsat=1)

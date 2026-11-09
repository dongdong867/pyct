"""The harness demands the summary line, measures a pyct child only when its deadline is off,
and narrows a printed line's fields, failing on a field of the wrong type."""

import json
import re
import subprocess

import pytest

from tests.acceptance.harness import (
    answered,
    argument,
    check_every_uncovered_line_explained_once,
    forks_of,
    input_lines,
    lines_expressions_and_sides,
    numbers_of,
    run_pyct,
    took,
    union_of,
)


def test_input_lines_demands_the_summary() -> None:
    # a run that lost its summary would otherwise read as one plain input line
    with pytest.raises(AssertionError):
        input_lines('{"args": {"x": 3}}\n')


def summary_with(uncovered: dict[str, list[int]], why: list[dict[str, object]]) -> str:
    """A run's stdout that ends on a summary with these uncovered lines and causes."""
    return json.dumps({"stopped": "no fork to flip", "uncovered": uncovered, "why_uncovered": why})


def test_the_check_passes_every_line_explained_once() -> None:
    why: list[dict[str, object]] = [
        {"file": "m.py", "lines": [1, 3], "reason": "import"},
        {"file": "m.py", "lines": [2], "reason": "ended before"},
    ]
    check_every_uncovered_line_explained_once(summary_with({"m.py": [1, 2, 3]}, why))


@pytest.mark.parametrize(
    "why",
    [
        # line 3 has no cause
        [{"file": "m.py", "lines": [1, 2], "reason": "import"}],
        # line 2 has two
        [
            {"file": "m.py", "lines": [1, 2, 3], "reason": "import"},
            {"file": "m.py", "lines": [2], "reason": "handler"},
        ],
        # a cause for a file the run did not measure
        [
            {"file": "m.py", "lines": [1, 2, 3], "reason": "import"},
            {"file": "n.py", "lines": [1], "reason": "import"},
        ],
    ],
)
def test_the_check_fails_a_line_left_out_or_named_twice(why: list[dict[str, object]]) -> None:
    with pytest.raises(AssertionError):
        check_every_uncovered_line_explained_once(summary_with({"m.py": [1, 2, 3]}, why))


def test_the_check_skips_a_run_with_no_summary() -> None:
    check_every_uncovered_line_explained_once("")
    check_every_uncovered_line_explained_once('{"args": {"x": 3}}\n')


def environment_for(
    monkeypatch: pytest.MonkeyPatch, *argv: str, timeout: float = 30
) -> dict[str, str]:
    """The environment ``run_pyct`` hands a child for ``argv``, read without starting one."""
    monkeypatch.setenv("COVERAGE_PROCESS_CONFIG", "{}")
    monkeypatch.setenv("COVERAGE_PROCESS_START", "pyproject.toml")
    handed: dict[str, str] = {}

    def spawn(command: list[str], **options: object) -> subprocess.CompletedProcess[str]:
        env = options["env"]
        assert isinstance(env, dict)
        handed.update(env)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", spawn)
    run_pyct(*argv, timeout=timeout)
    return handed


@pytest.mark.parametrize("budget", [("--budget", "1"), ("--budget=1",)], ids=["apart", "joined"])
def test_a_run_with_a_budget_starts_no_coverage(
    monkeypatch: pytest.MonkeyPatch, budget: tuple[str, ...]
) -> None:
    env = environment_for(monkeypatch, "m::f", "{}", *budget)

    assert "COVERAGE_PROCESS_CONFIG" not in env
    assert "COVERAGE_PROCESS_START" not in env


@pytest.mark.parametrize(
    "budget", [("--budget", "none"), ("--budget=none",)], ids=["apart", "joined"]
)
def test_a_run_with_budget_none_is_measured(
    monkeypatch: pytest.MonkeyPatch, budget: tuple[str, ...]
) -> None:
    env = environment_for(monkeypatch, "m::f", "{}", *budget)

    assert env["COVERAGE_PROCESS_START"] == "pyproject.toml"


@pytest.mark.parametrize(
    ("budgets", "measured"),
    [(("--budget", "none", "--budget", "1"), False), (("--budget=1", "--budget=none"), True)],
    ids=["seconds-last", "none-last"],
)
def test_the_last_budget_decides_as_the_command_line_reads_it(
    monkeypatch: pytest.MonkeyPatch, budgets: tuple[str, ...], measured: bool
) -> None:
    env = environment_for(monkeypatch, "m::f", "{}", *budgets)

    assert ("COVERAGE_PROCESS_START" in env) is measured, env


def test_a_run_with_no_budget_and_a_timeout_past_its_default_fails_before_it_starts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(pytest.fail.Exception, match="pass --budget none: a run with no flag"):
        environment_for(monkeypatch, "m::f", "{}", timeout=46)


@pytest.mark.parametrize(
    "budget", [(), ("--budget", "none"), ("--budget", "60")], ids=["at-45", "none", "seconds"]
)
def test_a_long_timeout_runs_with_a_budget_or_none_or_at_most_45_seconds(
    monkeypatch: pytest.MonkeyPatch, budget: tuple[str, ...]
) -> None:
    timeout = 45 if not budget else 120
    assert environment_for(monkeypatch, "m::f", "{}", *budget, timeout=timeout)


def test_a_run_without_a_budget_is_measured(monkeypatch: pytest.MonkeyPatch) -> None:
    # `--budgetless` gives no budget of seconds, so the run is measured
    env = environment_for(monkeypatch, "m::f", "{}", "--budgetless")

    assert env["COVERAGE_PROCESS_CONFIG"] == "{}"
    assert env["COVERAGE_PROCESS_START"] == "pyproject.toml"


def test_argument_reads_an_int_argument() -> None:
    assert argument({"args": {"x": 3}}, "x") == 3


@pytest.mark.parametrize(
    "line",
    [{"args": [3]}, {"args": {"x": "3"}}],
    ids=["args-not-a-dict", "argument-not-an-int"],
)
def test_argument_fails_a_malformed_line(line: dict[str, object]) -> None:
    with pytest.raises(AssertionError, match=re.escape(str(line))):
        argument(line, "x")


def test_forks_of_copies_each_fork() -> None:
    fork: dict[str, object] = {"line": 4, "expression": [">", "x", 0], "taken": True}

    (found,) = forks_of({"forks": [fork]})

    assert found == fork
    assert found is not fork


def test_forks_of_fails_forks_that_are_not_a_list() -> None:
    line: dict[str, object] = {"forks": {"line": 4}}
    with pytest.raises(AssertionError, match=re.escape(str(line))):
        forks_of(line)


def test_numbers_of_reads_a_map_of_line_numbers() -> None:
    assert numbers_of({"covered": {"m.py": [1, 2]}}, "covered") == {"m.py": [1, 2]}


def test_numbers_of_fails_a_map_that_is_not_a_dict() -> None:
    line: dict[str, object] = {"covered": [1, 2]}
    with pytest.raises(AssertionError, match=re.escape(str(line))):
        numbers_of(line, "covered")


def test_union_of_adds_up_every_covered_map() -> None:
    lines: list[dict[str, object]] = [
        {"covered": {"m.py": [3, 1]}},
        {"covered": {"m.py": [2, 3], "n.py": [5]}},
    ]

    assert union_of(lines) == {"m.py": [1, 2, 3], "n.py": [5]}


def test_union_of_fails_a_covered_map_that_is_not_a_dict() -> None:
    line: dict[str, object] = {"covered": [1]}
    with pytest.raises(AssertionError, match=re.escape(str(line))):
        union_of([{"covered": {"m.py": [1]}}, line])


def test_took_finds_a_fork_by_its_line_expression_and_side() -> None:
    lines: list[dict[str, object]] = [
        {"forks": [{"line": 4, "expression": "x", "taken": False}]},
        {"forks": [{"line": 4, "expression": "x", "taken": True}]},
    ]

    assert lines_expressions_and_sides(lines[1]) == [(4, "x", True)]
    assert took(lines, (4, "x", True))
    assert not took(lines, (5, "x", True))
    assert not took(lines, (4, "y", True))
    assert not took(lines[:1], (4, "x", True))


def _line(failure: object, mismatch_at: int | None, forks: int) -> dict[str, object]:
    return {"failure": failure, "mismatch_at": mismatch_at, "forks": [{}] * forks}


_CUT = {"kind": "timeout", "detail": "deadline passed"}


def test_answered_leaves_out_a_last_input_the_deadline_cut_where_it_stopped() -> None:
    ran = _line(None, None, 2)

    assert answered([ran, _line(_CUT, 3, 3)]) == [ran]
    assert answered([ran, _line(_CUT, None, 3)]) == [ran]
    assert answered([]) == []


def test_answered_keeps_every_other_line() -> None:
    ran = _line(None, None, 2)
    # left its plan before the deadline cut it, at a fork it took
    departed = _line(_CUT, 1, 3)
    too_long = _line({"kind": "too_long", "detail": "the journal is full at 9 bytes"}, 3, 3)
    other_timeout = _line({"kind": "timeout", "detail": "something else"}, 3, 3)

    assert answered([_line(_CUT, 3, 3), ran]) == [_line(_CUT, 3, 3), ran]
    assert answered([ran, departed]) == [ran, departed]
    assert answered([ran, too_long]) == [ran, too_long]
    assert answered([ran, other_timeout]) == [ran, other_timeout]

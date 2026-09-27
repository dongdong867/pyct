"""The harness demands the summary line, and measures a pyct child only when its deadline is off."""

import json
import subprocess

import pytest

from tests.acceptance.harness import (
    check_every_uncovered_line_explained_once,
    input_lines,
    run_pyct,
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


def environment_for(monkeypatch: pytest.MonkeyPatch, *argv: str) -> dict[str, str]:
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
    run_pyct(*argv)
    return handed


@pytest.mark.parametrize("budget", [("--budget", "1"), ("--budget=1",)], ids=["apart", "joined"])
def test_a_run_with_a_budget_starts_no_coverage(
    monkeypatch: pytest.MonkeyPatch, budget: tuple[str, ...]
) -> None:
    env = environment_for(monkeypatch, "m::f", "{}", *budget)

    assert "COVERAGE_PROCESS_CONFIG" not in env
    assert "COVERAGE_PROCESS_START" not in env


def test_a_run_without_a_budget_is_measured(monkeypatch: pytest.MonkeyPatch) -> None:
    # a flag that only starts like --budget sets no deadline
    env = environment_for(monkeypatch, "m::f", "{}", "--budgetless")

    assert env["COVERAGE_PROCESS_CONFIG"] == "{}"
    assert env["COVERAGE_PROCESS_START"] == "pyproject.toml"

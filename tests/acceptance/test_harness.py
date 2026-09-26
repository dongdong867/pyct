"""The harness demands the summary line, and measures a pyct child only when its deadline is off."""

import subprocess

import pytest

from tests.acceptance.harness import input_lines, run_pyct


def test_input_lines_demands_the_summary() -> None:
    # a run that lost its summary would otherwise read as one plain input line
    with pytest.raises(AssertionError):
        input_lines('{"args": {"x": 3}}\n')


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

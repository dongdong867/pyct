"""Acceptance tests for stop-a-run-with-no-budget-flag-after-45-seconds.

``pyct run`` with no ``--budget`` gets the limits a ``--budget 45`` run gets, and ``--budget
none`` gives a run, or each sweep entry, no deadline. No test waits 45 s: the in-process tests
read the limits ``main`` hands ``run()``, and ``test_stops_when_an_input_spends_the_budget`` in
``test_finish_a_run`` shows those limits stop a run at its deadline with ``budget spent``.
"""

import pytest

from pyct import cli
from pyct.cli import main, parse_command
from pyct.cli import sweep as sweep_command
from pyct.config.budget import Budget
from pyct.config.limits import Limits
from pyct.sweep.result import SweepLimits, SweepResult, SweepStop
from pyct.sweep.sweep import Mode, SweepTell
from tests.acceptance.harness import (
    input_lines,
    let_pyct_run_in_process,
    run_pyct,
    summary_line,
    without_seconds,
)
from tests.acceptance.sweeping import FIXTURES, rows, summary, sweep

# ``return "impossible"`` is a line no input reaches: the run ends by itself with a cause for it
IMPLIED_CHECK = "targets.flip.implied_check::narrow"
SEED = '{"x": 3}'


class LimitsHandedError(Exception):
    """Raised in place of the run, holding the limits ``main`` handed it."""

    def __init__(self, limits: Limits) -> None:
        super().__init__(limits)
        self.limits = limits


def limits_handed(monkeypatch: pytest.MonkeyPatch, *flags: str) -> Limits:
    """The limits ``pyct run`` with ``flags`` hands ``run()``, which never starts."""
    let_pyct_run_in_process(monkeypatch)

    def run(*_args: object, limits: Limits, **_kwargs: object) -> None:
        raise LimitsHandedError(limits)

    monkeypatch.setattr(cli, "run", run)
    with pytest.raises(LimitsHandedError) as handed:
        main(["run", IMPLIED_CHECK, SEED, *flags])
    return handed.value.limits


def sweep_limits(monkeypatch: pytest.MonkeyPatch, *flags: str) -> SweepLimits:
    """The limits ``pyct sweep p`` with ``flags`` hands the sweep, which finds nothing."""
    seen: list[SweepLimits] = []

    def found_nothing(
        package: str, *, limits: SweepLimits, mode: Mode, tell: SweepTell
    ) -> SweepResult:
        seen.append(limits)
        return SweepResult(package, (), SweepStop.DONE, limits)

    monkeypatch.setattr(sweep_command, "sweep", found_nothing)
    assert main(["sweep", "p", *flags]) == 0
    return seen[0]


def printed(stdout: str) -> list[dict[str, object]]:
    """Every stdout line, the summary's included, without the seconds no two runs share."""
    return [*map(without_seconds, input_lines(stdout)), without_seconds(summary_line(stdout))]


# run-budget-by-default-stops-a-run-that-never-ends
def test_a_run_with_no_flag_gets_the_limits_of_a_45_second_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unflagged = limits_handed(monkeypatch)

    assert unflagged == limits_handed(monkeypatch, "--budget", "45")
    assert unflagged.budget == Budget(seconds=45.0)


# run-budget-by-default-keeps-a-run-that-ends-by-itself
def test_a_run_that_ends_by_itself_ends_as_a_run_with_no_deadline() -> None:
    unflagged = run_pyct(IMPLIED_CHECK, SEED)
    unbounded = run_pyct(IMPLIED_CHECK, SEED, "--budget", "none")

    assert unflagged.returncode == 0, unflagged.stderr
    assert unbounded.returncode == 0, unbounded.stderr
    lines = printed(unflagged.stdout)
    assert lines == printed(unbounded.stdout)
    assert lines[-1]["stopped"] == "no fork to flip", lines[-1]
    assert lines[-1]["why_uncovered"], lines[-1]


# run-budget-none-has-no-deadline
def test_a_run_with_budget_none_gets_no_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    assert limits_handed(monkeypatch, "--budget", "none") == Limits()


# run-budget-none-for-each-sweep-entry
def test_a_sweep_with_budget_none_runs_each_entry_with_no_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert sweep_limits(monkeypatch, "--budget", "none").budget is None

    result = sweep(f"{FIXTURES}.pair", "--budget", "none")

    assert result.returncode == 0, result.stderr
    # the pair's third entry takes no parameter, so it is skipped before any run
    statuses = {row["name"]: row["status"] for row in rows(result.stdout)}
    assert statuses == {"first": "ran", "second": "ran", "third": "skipped"}, statuses
    assert summary(result.stdout)["limits"]["budget"] is None


# run-budget-none-sweep-default-stays-30
def test_a_sweep_with_no_flag_still_gives_each_entry_30_seconds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert sweep_limits(monkeypatch).budget == 30.0


def help_of(capsys: pytest.CaptureFixture[str], command: str) -> str:
    with pytest.raises(SystemExit):
        parse_command([command, "--help"])
    return " ".join(capsys.readouterr().out.split())


# run-budget-help-run
def test_the_run_help_says_45_seconds_by_default_and_none(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert "--budget SECONDS the run's seconds; 45 by default, none for no deadline" in help_of(
        capsys, "run"
    )


# run-budget-help-sweep
def test_the_sweep_help_says_none(capsys: pytest.CaptureFixture[str]) -> None:
    said = help_of(capsys, "sweep")

    assert "--budget SECONDS each entry's budget; 30 by default, none for no deadline" in said
    # the total budget takes no `none`, so its help does not offer one
    assert "--total-budget SECONDS the whole sweep's bound; no bound by default" in said


# today's refusal of each value, by whether float() reads it
REFUSED = {
    **dict.fromkeys(["None", "NONE", "abc"], "a number of seconds"),
    **dict.fromkeys(["0", "-1", "inf", "nan"], "a finite number of seconds above zero"),
}


# run-budget-refused-bad-value
@pytest.mark.parametrize("text", ["None", "NONE", "abc", "0", "-1", "inf", "nan"])
@pytest.mark.parametrize("command", ["run", "sweep"])
def test_any_other_budget_is_a_usage_error(
    command: str, text: str, capsys: pytest.CaptureFixture[str]
) -> None:
    head = ["run", IMPLIED_CHECK, SEED] if command == "run" else ["sweep", "p"]

    assert main([*head, "--budget", text]) == 2

    said = capsys.readouterr()
    assert said.out == ""
    assert said.err == f"budget must be {REFUSED[text]}, got {text!r}\n"


# run-budget-refused-total-budget-none
def test_a_total_budget_of_none_is_still_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["sweep", "p", "--total-budget", "none"]) == 2

    said = capsys.readouterr()
    assert said.out == ""
    assert said.err == "total budget must be a number of seconds, got 'none'\n"

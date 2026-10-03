"""Acceptance tests for print-an-input-with-many-forks-within-its-budget.

Each test spawns ``python -P -m pyct`` on the countdown loop, whose fork on each pass holds
the condition every pass before it built, and measures the run from launch to exit: its wall
time, its CPU time summed over pyct's process and every process it waited for, and the largest
peak memory among them. The budgets are shorter than the criteria's 20 seconds, so the suite
stays quick; the bounds they check scale with them.

The criteria bound the wall time from launch, and the tests hold them there: a run that misses
its wall bound is run again, up to three runs, and the test fails only when none is within it,
so a slow moment of a loaded machine fails no test and a run that is always late still does
(see ``tests.acceptance.timed``). The same bounds are also held in CPU seconds: pyct's process
mostly waits while an input runs, so on an idle machine their CPU time is about the wall time,
and a loaded machine stretches it far less. It reads the input's facts while it waits, which
adds to the CPU time of an input that runs long.
"""

import json
from pathlib import Path

import pytest

from tests.acceptance.harness import REPO_ROOT, forks_of, input_lines, summary_line
from tests.acceptance.timed import Measured, measured, within

COUNTDOWN = "targets.loops.countdown::count_down"
COUNTDOWN_FILE = str(REPO_ROOT / "targets" / "loops" / "countdown.py")

# the line's budget of expression nodes, as the criteria write it
LINE_NODES = 100_000


def _measured(tmp_path: Path, seed: int, budget: str) -> Measured:
    """One run of the countdown loop from ``seed``, with ``budget`` seconds."""
    return measured(tmp_path, _countdown(seed, budget))


def _within(tmp_path: Path, seed: int, budget: str, wall: float) -> Measured:
    """The first of up to three runs whose wall time is under ``wall``, or the last run."""
    return within(tmp_path, _countdown(seed, budget), lambda run: run.wall < wall)


def _countdown(seed: int, budget: str) -> list[str]:
    return [COUNTDOWN, "--args", json.dumps({"x": seed}), "--budget", budget]


def _inputs(stdout: str) -> int:
    """How many inputs the summary line says the run ran."""
    inputs = summary_line(stdout)["inputs"]
    assert isinstance(inputs, int)
    return inputs


def _nodes(expression: object) -> int:
    """Nodes as the line writes them: a list and each of its operands."""
    if not isinstance(expression, list):
        return 1
    return 1 + sum(_nodes(part) for part in expression[1:])


def _pass(i: int) -> object:
    """The countdown's fork on pass i: `x - 1 - ... - 1 > 0`, i subtractions."""
    value: object = "x"
    for _ in range(i):
        value = ["-", value, 1]
    return [">", value, 0]


@pytest.fixture(scope="module")
def ten_thousand_passes(tmp_path_factory: pytest.TempPathFactory) -> Measured:
    """A run of a 10,000-pass seed, which two criteria read, within the first one's wall bound."""
    return _within(tmp_path_factory.mktemp("ten_thousand"), 10_000, "4", 4 + 1)


@pytest.mark.serial
# print-an-input-with-many-forks-within-its-budget-ends-a-long-loop-within-a-second
def test_a_long_loop_ends_within_a_second_of_its_budget(ten_thousand_passes: Measured) -> None:
    run = ten_thousand_passes

    assert run.returncode == 0, run.stderr[-2000:]
    # the criterion's 21 s for a 20 s budget: the one second the isolation rule gives
    assert run.wall < 4 + 1, run.wall
    assert run.cpu < 4 + 1, run.cpu
    assert _inputs(run.stdout) >= 3, _inputs(run.stdout)
    assert run.peak_bytes <= 400 * 1024 * 1024, run.peak_bytes
    forks = forks_of(input_lines(run.stdout)[0])
    places = {(fork["file"], fork["line"], fork["col"]) for fork in forks}
    assert len(forks) == 10_001
    assert places == {(COUNTDOWN_FILE, 2, 10)}


@pytest.mark.serial
# print-an-input-with-many-forks-within-its-budget-runs-more-inputs-at-two-thousand-passes
def test_two_thousand_passes_run_more_inputs(tmp_path: Path) -> None:
    run = _within(tmp_path, 2_000, "3", 3 + 1)

    assert run.returncode == 0, run.stderr[-2000:]
    assert run.wall < 3 + 1, run.wall
    assert run.cpu < 3 + 1, run.cpu
    # printing an input takes about as long as running it, not ten times as long
    assert _inputs(run.stdout) >= 8, _inputs(run.stdout)
    assert run.peak_bytes <= 300 * 1024 * 1024, run.peak_bytes


# print-an-input-with-many-forks-within-its-budget-keeps-a-short-line-as-it-was
def test_a_line_within_its_budget_prints_as_it_did(tmp_path: Path) -> None:
    run = _measured(tmp_path, 300, "2")

    assert run.returncode == 0, run.stderr[-2000:]
    # the 301 forks hold 91,203 nodes, within the line's budget, so each prints whole, as it
    # printed before the line had a budget
    forks = forks_of(input_lines(run.stdout)[0])
    assert [fork["expression"] for fork in forks] == [_pass(i) for i in range(301)]
    assert sum(_nodes(fork["expression"]) for fork in forks) == 91_203
    seed_trace = run.stderr.split("\nsolver ", 1)[0].splitlines()
    fork_lines = [line for line in seed_trace if line.startswith("fork ")]
    site = f"fork {COUNTDOWN_FILE}:2:10  "
    assert fork_lines == [
        f"{site}x{' - 1' * i} > 0  {'taken' if i < 300 else 'not taken'}" for i in range(301)
    ]
    after = seed_trace[seed_trace.index(fork_lines[-1]) + 1]
    assert after.startswith("covered "), after


# its fixture's runs are held to a wall bound, so it runs alone, whichever test takes it first
@pytest.mark.serial
# print-an-input-with-many-forks-within-its-budget-cuts-forks-past-the-line-budget
def test_forks_past_the_line_budget_print_one_cut_part_each(
    ten_thousand_passes: Measured,
) -> None:
    run = ten_thousand_passes
    forks = forks_of(input_lines(run.stdout)[0])

    kept = [fork["expression"] for fork in forks[:315]]
    assert kept == [_pass(i) for i in range(315)]
    assert sum(_nodes(expression) for expression in kept) == 99_855
    cut = [fork["expression"] for fork in forks[315:]]
    assert all(
        expression in (["...", 2 * i + 3], ["...", None])
        for i, expression in enumerate(cut, start=315)
    )
    trace = run.stderr.split("\nsolver ", 1)[0].splitlines()
    fork_lines = [line for line in trace if line.startswith("fork ")]
    site = f"fork {COUNTDOWN_FILE}:2:10  "
    assert fork_lines[315] == f"{site}...({2 * 315 + 3} nodes)  taken"
    assert fork_lines[-1] == f"{site}...({2 * 10_000 + 3} nodes)  not taken"
    after = trace[trace.index(fork_lines[-1]) + 1]
    assert after == (
        f"cut the expressions of 9686 forks, from position 315 on, past the line's "
        f"{LINE_NODES:,} nodes"
    )


@pytest.mark.serial
# print-an-input-with-many-forks-within-its-budget-ends-a-seed-stopped-at-its-deadline
def test_a_seed_stopped_at_its_deadline_ends_soon_after(tmp_path: Path) -> None:
    run = _within(tmp_path, 100_000_000, "1", 2)

    assert run.returncode == 0, run.stderr[-2000:]
    # the criterion's bound, two seconds from launch: the one second the isolation rule gives
    assert run.wall < 2, run.wall
    # pyct's process reads the input's facts while the input runs its one second, so the two
    # processes' CPU time can pass the wall time by up to the budget
    assert run.cpu < 2 + 1, run.cpu
    seed = input_lines(run.stdout)[0]
    assert seed["failure"] == {"kind": "timeout", "detail": "deadline passed"}
    fork_lines = [line for line in run.stderr.splitlines() if line.startswith("fork ")]
    assert len(forks_of(seed)) == len(fork_lines) > 10_000
    assert run.stderr.splitlines()[-1] == "stopped: budget spent"
    assert run.peak_bytes <= 400 * 1024 * 1024, run.peak_bytes

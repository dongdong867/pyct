"""Acceptance tests for print-an-input-with-many-forks-within-its-budget.

Each test spawns ``python -P -m pyct`` on the countdown loop, whose fork on each pass holds
the condition every pass before it built, and measures the run from launch to exit: its CPU
time and its peak memory, pyct's process and every input's together, and its wall time. The
budgets are shorter than the criteria's 20 seconds, so the suite stays quick; the bounds they
check scale with them.

The criteria's time bounds are held in CPU seconds: the run's processes run one at a time, so
on an idle machine their CPU time is about the wall time, and a loaded machine, which stretches
the wall time, leaves it be. The wall time gets ``_LOADED`` more seconds, so a run that waits
that long without working still fails.
"""

import json
import os
import resource
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.acceptance.harness import COVERAGE_STARTUP, REPO_ROOT, input_lines, summary_line
from tests.acceptance.test_strs import forks_of

COUNTDOWN = "targets.loops.countdown::count_down"
COUNTDOWN_FILE = str(REPO_ROOT / "targets" / "loops" / "countdown.py")

# the line's budget of expression nodes, as the criteria write it
LINE_NODES = 100_000

# how often the wait looks at the child, which bounds what the wall time overstates
_POLL = 0.01

# the seconds a loaded machine may add to a run's wall time, past a criterion's bound
_LOADED = 10


@dataclass(frozen=True)
class Measured:
    """What one run printed, how it exited, and what it cost."""

    stdout: str
    stderr: str
    returncode: int
    wall: float
    cpu: float
    peak_bytes: int


def _measured(tmp_path: Path, seed: int, budget: str, *, timeout: float = 45) -> Measured:
    """Run pyct on the countdown loop, from launch to exit, with its CPU time and peak memory.

    Like the harness, it leaves coverage.py out of a run with a budget. The wait
    reads the resource use of pyct's process and of every input process it
    waited for, as ``/usr/bin/time`` does.
    """
    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", *COVERAGE_STARTUP}}
    argv = [sys.executable, "-P", "-m", "pyct", "run", COUNTDOWN, "--args", json.dumps({"x": seed})]
    out, err = tmp_path / "out", tmp_path / "err"
    with out.open("w") as stdout, err.open("w") as stderr:
        start = time.monotonic()
        child = subprocess.Popen(
            [*argv, "--budget", budget], cwd=REPO_ROOT, env=env, stdout=stdout, stderr=stderr
        )
        status, usage = _waited(child, start + timeout)
        wall = time.monotonic() - start
    # macOS counts the peak in bytes, Linux in KiB
    unit = 1 if sys.platform == "darwin" else 1024
    return Measured(
        out.read_text(),
        err.read_text(),
        os.waitstatus_to_exitcode(status),
        wall,
        usage.ru_utime + usage.ru_stime,
        usage.ru_maxrss * unit,
    )


def _waited(child: subprocess.Popen[bytes], until: float) -> tuple[int, resource.struct_rusage]:
    """The child's exit status and resource use, or a failed test when it outlives ``until``."""
    while time.monotonic() < until:
        pid, status, usage = os.wait4(child.pid, os.WNOHANG)
        if pid:
            child.returncode = os.waitstatus_to_exitcode(status)
            return status, usage
        time.sleep(_POLL)
    child.kill()
    child.wait()
    pytest.fail("pyct ran past the test's own limit")


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
    """One run of a 10,000-pass seed, which two criteria read."""
    return _measured(tmp_path_factory.mktemp("ten_thousand"), 10_000, "4")


# print-an-input-with-many-forks-within-its-budget-ends-a-long-loop-within-a-second
def test_a_long_loop_ends_within_a_second_of_its_budget(ten_thousand_passes: Measured) -> None:
    run = ten_thousand_passes

    assert run.returncode == 0, run.stderr[-2000:]
    # the criterion's 21 s for a 20 s budget: the one second the isolation rule gives
    assert run.cpu < 4 + 1, run.cpu
    assert run.wall < 4 + 1 + _LOADED, run.wall
    assert _inputs(run.stdout) >= 3, _inputs(run.stdout)
    assert run.peak_bytes <= 400 * 1024 * 1024, run.peak_bytes
    forks = forks_of(input_lines(run.stdout)[0])
    places = {(fork["file"], fork["line"], fork["col"]) for fork in forks}
    assert len(forks) == 10_001
    assert places == {(COUNTDOWN_FILE, 2, 10)}


# print-an-input-with-many-forks-within-its-budget-runs-more-inputs-at-two-thousand-passes
def test_two_thousand_passes_run_more_inputs(tmp_path: Path) -> None:
    run = _measured(tmp_path, 2_000, "3")

    assert run.returncode == 0, run.stderr[-2000:]
    assert run.cpu < 3 + 1, run.cpu
    assert run.wall < 3 + 1 + _LOADED, run.wall
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


# print-an-input-with-many-forks-within-its-budget-ends-a-seed-stopped-at-its-deadline
def test_a_seed_stopped_at_its_deadline_ends_soon_after(tmp_path: Path) -> None:
    run = _measured(tmp_path, 100_000_000, "1")

    assert run.returncode == 0, run.stderr[-2000:]
    # the criterion's bound, three seconds from launch: reading the input's journal of about
    # 100,000 forks takes the rest of the second the isolation rule gives
    assert run.cpu < 3, run.cpu
    assert run.wall < 3 + _LOADED, run.wall
    seed = input_lines(run.stdout)[0]
    assert seed["failure"] == {"kind": "timeout", "detail": "deadline passed"}
    fork_lines = [line for line in run.stderr.splitlines() if line.startswith("fork ")]
    assert len(forks_of(seed)) == len(fork_lines) > 10_000
    assert run.stderr.splitlines()[-1] == "stopped: budget spent"
    assert run.peak_bytes <= 400 * 1024 * 1024, run.peak_bytes

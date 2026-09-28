"""Acceptance tests for the keep-the-deadline-alarm-inside-its-call bug.

The first four criteria each make ``run()`` calls for 30 seconds in a process of
their own, ``tests/acceptance/deadline_race.py``, whose SIGALRM handler is
SIG_DFL or a counting one of its own; a fifth race does the same in a process
pyct owns, as the command line's. The five processes start together the first
time a test asks for one, so the race tests take about 30 seconds in all, in
the one worker of a parallel run that holds this module.

The last criterion runs pyct from the command line. The C-bound tests pin the
split by owner: the command line's process takes the kernel timer, whose
signal a C call that checks for signals meets, and a guest's watcher thread
waits for the GIL until the call returns.
"""

import json
import os
import subprocess
import sys
import time
from collections.abc import Iterator

import pytest

from targets.isolate.hangs_with_finally import MARKER
from tests.acceptance.harness import COVERAGE_STARTUP, REPO_ROOT, first_line, run_pyct, summary_line

# one worker holds the races, so a parallel run starts each race process once
pytestmark = pytest.mark.xdist_group("deadline-races")

# how long each race process makes runs
RACE_SECONDS = 30
# the least share of seeds that must end each way, so the runs raced the instant
EACH_WAY = 0.15
HANGS = "targets.isolate.hangs_with_finally::hang"
C_WORK = "targets.isolate.c_work"
HOLDS_A_CTRL_C = "targets.isolate.holds_a_ctrl_c::hold"


@pytest.fixture(scope="module")
def races() -> Iterator[dict[str, subprocess.Popen[str]]]:
    """The four race processes, started together and killed at the end if still running."""
    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", *COVERAGE_STARTUP}}
    started = {
        case: subprocess.Popen(
            [sys.executable, "-m", "tests.acceptance.deadline_race", case, str(RACE_SECONDS)],
            cwd=REPO_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for case in ("in-process", "counted", "owned", "forked", "past-the-kill")
    }
    yield started
    for process in started.values():
        if process.poll() is None:
            process.kill()
            process.wait()


def raced(races: dict[str, subprocess.Popen[str]], case: str) -> dict[str, object]:
    """What one race process printed, once it exited 0, never by SIGALRM."""
    stdout, stderr = races[case].communicate(timeout=RACE_SECONDS + 60)
    assert races[case].returncode == 0, (races[case].returncode, stderr)
    tally = json.loads(stdout)
    assert tally["bad"] == [], tally
    total = tally["returned"] + tally["timeout"]
    # about half each way: the calls ended on both sides of the instant they raced
    assert tally["returned"] >= EACH_WAY * total, tally
    assert tally["timeout"] >= EACH_WAY * total, tally
    return tally


# keep-the-deadline-alarm-inside-its-call-never-ends-the-process
def test_never_ends_the_process(races: dict[str, subprocess.Popen[str]]) -> None:
    raced(races, "in-process")


# keep-the-deadline-alarm-inside-its-call-leaves-the-caller-s-handler-alone
def test_leaves_the_caller_s_handler_alone(races: dict[str, subprocess.Popen[str]]) -> None:
    tally = raced(races, "counted")

    assert tally["counted"] == 0, tally
    assert tally["handler_moved"] == 0, tally


def test_a_process_pyct_owns_keeps_each_in_process_alarm_inside_its_call(
    races: dict[str, subprocess.Popen[str]],
) -> None:
    tally = raced(races, "owned")

    assert tally["handler_moved"] == 0, tally


# keep-the-deadline-alarm-inside-its-call-keeps-a-forked-input-s-ending
def test_keeps_a_forked_input_s_ending(races: dict[str, subprocess.Popen[str]]) -> None:
    raced(races, "forked")


# keep-the-deadline-alarm-inside-its-call-keeps-pyct-s-process-past-the-kill
def test_keeps_pyct_s_process_past_the_kill(races: dict[str, subprocess.Popen[str]]) -> None:
    raced(races, "past-the-kill")


# keep-the-deadline-alarm-inside-its-call-still-stops-a-hang
@pytest.mark.parametrize("where", [(), ("--in-process",)], ids=["own-process", "in-process"])
def test_still_stops_a_hang(where: tuple[str, ...]) -> None:
    started = time.monotonic()
    result = run_pyct(HANGS, '{"x": 0}', "--budget", "1", *where)
    took = time.monotonic() - started

    assert result.returncode == 0, result.stderr
    assert first_line(result.stdout)["failure"] == {"kind": "timeout", "detail": "deadline passed"}
    assert MARKER in result.stderr
    assert summary_line(result.stdout)["stopped"] == "budget spent"
    assert took < 2.0, took


@pytest.mark.parametrize("name", ["backtrack", "power"])
def test_the_command_line_stops_a_c_call_that_checks_for_signals_at_its_deadline(
    name: str,
) -> None:
    started = time.monotonic()
    result = run_pyct(f"{C_WORK}::{name}", '{"x": 0}', "--in-process", "--budget", "0.2")
    took = time.monotonic() - started

    assert result.returncode == 0, result.stderr
    assert first_line(result.stdout)["failure"] == {"kind": "timeout", "detail": "deadline passed"}
    # the call alone takes over two seconds where it is not stopped
    assert took < 1.5, took


@pytest.mark.parametrize("name", ["backtrack", "power"])
def test_a_guest_run_lets_a_c_call_that_holds_the_gil_run_to_its_end(name: str) -> None:
    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", *COVERAGE_STARTUP}}

    finished = subprocess.run(
        [sys.executable, "-m", "tests.acceptance.guest_c_work", f"{C_WORK}::{name}"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )

    assert finished.returncode == 0, finished.stderr
    ran = json.loads(finished.stdout)
    # the watcher needs the GIL to send, so the 0.1 s deadline waits for the call to return,
    # and its alarm lands as the target returns or just after
    assert ran["kind"] in (None, "timeout"), ran
    assert ran["took"] > 1.5, ran


def test_the_command_line_ends_a_call_that_never_lets_a_ctrl_c_go() -> None:
    started = time.monotonic()
    result = run_pyct(HOLDS_A_CTRL_C, '{"x": 0}', "--in-process", "--budget", "0.2")
    took = time.monotonic() - started

    assert result.returncode == 0, result.stderr
    assert first_line(result.stdout)["failure"] == {"kind": "timeout", "detail": "deadline passed"}
    # the alarm waits for the Ctrl-C at most half a second past the deadline
    assert took < 2.0, took

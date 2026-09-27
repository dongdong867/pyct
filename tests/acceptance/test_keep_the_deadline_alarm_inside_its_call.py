"""Acceptance tests for the keep-the-deadline-alarm-inside-its-call bug.

The first four criteria each make ``run()`` calls for 30 seconds in a process of
their own, ``tests/acceptance/deadline_race.py``, whose SIGALRM handler is
SIG_DFL or a counting one of its own. The four processes start together the
first time a test asks for one, so the four tests take about 30 seconds in all.
The last criterion runs pyct from the command line.
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

# how long each race process makes runs
RACE_SECONDS = 30
# the least share of seeds that must end each way, so the runs raced the instant
EACH_WAY = 0.15
HANGS = "targets.isolate.hangs_with_finally::hang"


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
        for case in ("in-process", "counted", "forked", "past-the-kill")
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

"""Acceptance tests for let-a-ctrl-c-win-over-the-deadline-under-a-host-tracer, one per criterion.

Each runs ``targets/isolate/traced.py`` under no tracer, a ``sys.settrace`` tracer or a
``sys.monitoring`` tool, in a process of its own without coverage.py, since the deadline raises
inside the tracer: through ``run()`` in a program that installs the tracer,
``tests/acceptance/traced_guest.py``, or through ``pyct run``, the tracer installed by the
target's import. The signal comes from the test once the call's C call has begun. Each test
times its runs, so it runs alone, after the parallel tests.
"""

import json
import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from targets.isolate.long_sum import TERMS
from targets.isolate.traced import MARKER
from tests.acceptance.harness import COVERAGE_STARTUP, REPO_ROOT, first_line

pytestmark = pytest.mark.serial

TRACERS = ["none", "settrace", "monitoring"]
CALLS = ["total", "total_then_finally"]
# the command's budget, and how long after the C call began a Ctrl-C comes: past the deadline,
# and inside a call that runs more than a second
BUDGET = "0.4"
CTRL_C_AFTER = 0.6
# how long before the C call's measured end a SIGTERM comes, well inside the guard's grace
SIGTERM_BEFORE_THE_END = 0.4


def unmeasured(**variables: str) -> dict[str, str]:
    """This process's variables without coverage.py's or ``PYTHONPATH``, with ``variables``."""
    left_out = {"PYTHONPATH", *COVERAGE_STARTUP}
    return {**{k: v for k, v in os.environ.items() if k not in left_out}, **variables}


def guest(tracer: str, name: str, tries: int, interrupt: bool) -> tuple[list[dict], str]:
    """The tries of ``traced_guest`` on ``name`` under ``tracer``, and its stderr."""
    ran = subprocess.run(
        [sys.executable, "-m", "tests.acceptance.traced_guest", tracer, name, str(tries)]
        + ["yes" if interrupt else "no"],
        cwd=REPO_ROOT,
        env=unmeasured(),
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert ran.returncode == 0, ran.stderr
    return [json.loads(line) for line in ran.stdout.splitlines()], ran.stderr


@pytest.fixture(scope="module")
def c_call_seconds() -> float:
    """How long the targets' C call takes on this Python and machine, measured here."""
    started = time.monotonic()
    sum(range(TERMS))
    return time.monotonic() - started


def interrupted(
    tracer: str,
    name: str,
    tmp_path: Path,
    send: Callable[[subprocess.Popen[str]], None],
    after: float,
) -> tuple[int, str, str]:
    """``pyct run --in-process`` on ``name`` in a session of its own, ``send`` called on it
    ``after`` seconds after its C call began: its exit code, stdout and stderr."""
    calling = tmp_path / "calling"
    env = unmeasured(PYCT_TEST_TRACER=tracer, PYCT_TEST_CALLING=str(calling))
    spec = f"targets.isolate.traced::{name}"
    argv = ["run", spec, "--args", '{"x": 0}', "--in-process", "--budget", BUDGET]
    process = subprocess.Popen(
        [sys.executable, "-P", "-m", "pyct", *argv],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        waited = time.monotonic() + 20
        while not calling.exists() and time.monotonic() < waited:
            time.sleep(0.01)
        time.sleep(after)
        send(process)
        stdout, stderr = process.communicate(timeout=30)
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
    return process.returncode, stdout, stderr


def timed_command(tracer: str, name: str, *flags: str) -> tuple[float, subprocess.CompletedProcess]:
    """``pyct run <name> --budget 1`` with ``flags``, ``tracer`` installed by the target's
    import, and the seconds from its start to its end."""
    started = time.monotonic()
    ran = subprocess.run(
        [sys.executable, "-P", "-m", "pyct", "run", f"targets.isolate.traced::{name}"]
        + ["--args", '{"x": 0}', "--budget", "1", *flags],
        cwd=REPO_ROOT,
        env=unmeasured(PYCT_TEST_TRACER=tracer),
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    return time.monotonic() - started, ran


def assert_timed_out(took: float, ran: subprocess.CompletedProcess) -> None:
    """The command's seed timed out, its finally ran, and it ended within 2 s, exit 0."""
    assert ran.returncode == 0, ran.stderr
    assert first_line(ran.stdout)["failure"] == {"kind": "timeout", "detail": "deadline passed"}
    assert MARKER in ran.stderr, ran.stderr
    assert took < 2, took


# let-a-ctrl-c-win-over-the-deadline-under-a-host-tracer-reaches-a-guest-caller
@pytest.mark.parametrize("name", CALLS)
@pytest.mark.parametrize("tracer", TRACERS)
def test_reaches_a_guest_caller(tracer: str, name: str) -> None:
    tries, stderr = guest(tracer, name, 3, interrupt=True)

    assert [one["ended"] for one in tries] == ["KeyboardInterrupt"] * 3, tries
    assert all(one["own_handler"] for one in tries), tries
    assert stderr.count(MARKER) == (3 if name == "total_then_finally" else 0), stderr


def ctrl_c(process: subprocess.Popen[str]) -> None:
    """A Ctrl-C from the terminal: SIGINT to the session's whole process group."""
    os.killpg(process.pid, signal.SIGINT)


def sigterm(process: subprocess.Popen[str]) -> None:
    """A SIGTERM to the pid the shell got."""
    os.kill(process.pid, signal.SIGTERM)


# let-a-ctrl-c-win-over-the-deadline-under-a-host-tracer-ends-pyct-in-process
@pytest.mark.parametrize("name", CALLS)
@pytest.mark.parametrize("tracer", TRACERS)
def test_ends_pyct_in_process(tracer: str, name: str, tmp_path: Path) -> None:
    code, stdout, stderr = interrupted(tracer, name, tmp_path, ctrl_c, CTRL_C_AFTER)

    assert code == -signal.SIGINT, stderr
    assert stderr.count("Traceback (most recent call last)") == 1, stderr
    assert stderr.rstrip().endswith("KeyboardInterrupt"), stderr
    assert not any("args" in json.loads(line) for line in stdout.splitlines()), stdout
    assert (MARKER in stderr) == (name == "total_then_finally"), stderr


# let-a-ctrl-c-win-over-the-deadline-under-a-host-tracer-lets-a-sigterm-win-too
@pytest.mark.parametrize("name", CALLS)
@pytest.mark.parametrize("tracer", TRACERS)
def test_lets_a_sigterm_win_too(
    tracer: str, name: str, tmp_path: Path, c_call_seconds: float
) -> None:
    # the guard ends a process a SIGTERM has not ended within its grace, so the call must
    # return within it for its finally to run: the SIGTERM comes shortly before its end
    after = max(CTRL_C_AFTER, c_call_seconds - SIGTERM_BEFORE_THE_END)
    code, stdout, stderr = interrupted(tracer, name, tmp_path, sigterm, after)

    assert code == -signal.SIGTERM, stderr
    assert not any("args" in json.loads(line) for line in stdout.splitlines()), stdout
    assert (MARKER in stderr) == (name == "total_then_finally"), stderr


# let-a-ctrl-c-win-over-the-deadline-under-a-host-tracer-still-times-out-a-loop-under-a-tracer
@pytest.mark.parametrize("tracer", TRACERS)
def test_still_times_out_a_loop_under_a_tracer(tracer: str) -> None:
    tries, stderr = guest(tracer, "loop", 1, interrupt=False)
    took, ran = timed_command(tracer, "loop", "--in-process")

    assert [one["ended"] for one in tries] == [["timeout", "deadline passed"]], tries
    assert tries[0]["took"] < 1.3, tries
    assert MARKER in stderr, stderr
    assert_timed_out(took, ran)


# let-a-ctrl-c-win-over-the-deadline-under-a-host-tracer-ends-a-hang-inside-the-tracer
@pytest.mark.parametrize("tracer", ["settrace", "monitoring"])
def test_ends_a_hang_inside_the_tracer(tracer: str) -> None:
    tries, stderr = guest(tracer, "in_the_tracer", 1, interrupt=False)
    commands = [timed_command(tracer, "in_the_tracer", *flags) for flags in ((), ("--in-process",))]

    assert [one["ended"] for one in tries] == [["timeout", "deadline passed"]], tries
    assert tries[0]["took"] < 1.3, tries
    assert MARKER in stderr, stderr
    for took, ran in commands:
        assert_timed_out(took, ran)

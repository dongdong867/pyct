"""What a signal sent to pyct does, now that pyct's work runs in a process of its own.

The process the shell started watches that process, so these tests send their signals to
the pid the shell got, as a person or a harness does, and check that the run and its input's
process end as they did when that pid was pyct's own.
"""

import os
import signal
import subprocess
import sys
import time
from collections.abc import Generator
from contextlib import contextmanager, suppress
from pathlib import Path

from tests.acceptance.harness import REPO_ROOT
from tests.acceptance.test_run_a_target_in_a_throwaway_process import (
    is_running,
    pid_written_to,
    pyct_in_a_session,
)

C_HANG = "targets.isolate.c_hang::stall"
SLOW_INPUTS = "targets.load.slow_inputs::f"
# how soon after the signal every process of the run must have ended
ENDED_WITHIN = 1.5


def group_ended(group: int) -> bool:
    """Whether no process of ``group`` is left, after a moment for the system to reap them.

    The system refuses to signal a group whose only processes are still
    exiting, so a refusal means to look again.
    """
    for _ in range(20):
        with suppress(PermissionError):
            try:
                os.killpg(group, 0)
            except ProcessLookupError:
                return True
        time.sleep(0.05)
    return False


# a SIGTERM ends the run, and the input's process with it, as a Ctrl-C does
def test_a_sigterm_ends_the_run_and_its_input(tmp_path: Path) -> None:
    pid_file = tmp_path / "pid"
    with pyct_in_a_session(C_HANG, pid_file) as process:
        child = pid_written_to(pid_file, process)
        sent = time.monotonic()
        os.kill(process.pid, signal.SIGTERM)
        process.wait(timeout=10)
        took = time.monotonic() - sent

        assert process.returncode == -signal.SIGTERM
        assert took < ENDED_WITHIN, took
        assert not is_running(child)
        assert group_ended(process.pid)


# the process the shell started is killed while an input hangs: the run and the input end
def test_a_sigkill_to_pyct_ends_the_run_and_its_input(tmp_path: Path) -> None:
    pid_file = tmp_path / "pid"
    with pyct_in_a_session(C_HANG, pid_file) as process:
        child = pid_written_to(pid_file, process)
        os.kill(process.pid, signal.SIGKILL)
        process.wait(timeout=10)

        assert not is_running(child)
        assert group_ended(process.pid)


def notes_in(path: Path) -> int:
    """How many inputs have noted their start in ``path``."""
    try:
        return len(path.read_text().splitlines())
    except FileNotFoundError:
        return 0


@contextmanager
def slow_run_in_a_session(notes: Path, out: Path) -> Generator[subprocess.Popen[bytes]]:
    """``pyct run`` on a target whose inputs are slow, stdout to a file, in a session of its own."""
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYCT_TEST_INPUTS"] = str(notes)
    with out.open("w") as stdout:
        process = subprocess.Popen(
            [sys.executable, "-P", "-m", "pyct", "run", SLOW_INPUTS, '{"x": -1}'],
            cwd=REPO_ROOT,
            env=env,
            stdout=stdout,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    try:
        yield process
    finally:
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)


# the process the shell started is killed between inputs: no further input starts
def test_a_sigkill_to_pyct_starts_no_further_input(tmp_path: Path) -> None:
    notes = tmp_path / "inputs"
    with slow_run_in_a_session(notes, tmp_path / "out") as process:
        deadline = time.monotonic() + 20
        while notes_in(notes) < 3 and time.monotonic() < deadline:
            time.sleep(0.02)
        os.kill(process.pid, signal.SIGKILL)
        started = notes_in(notes)
        process.wait(timeout=10)

        assert group_ended(process.pid)
        # an input starting as the kill landed may note itself; none after it
        assert notes_in(notes) <= started + 1
        time.sleep(0.5)
        assert notes_in(notes) <= started + 1

"""The process the shell started, which watches pyct's own process.

The signal tests send their signals to the pid the shell got, as a person or a harness
does, and check that the run and its input's process end as they did when that pid was
pyct's own. The thread tests start a thread before pyct runs, as a host's instrumentation
does from ``sitecustomize``.
"""

import json
import os
import signal
import subprocess
import sys
import time
from collections.abc import Generator
from contextlib import contextmanager, suppress
from pathlib import Path

import pytest

from pyct.run.guard import STOP_GRACE
from tests.acceptance.harness import REPO_ROOT, input_lines, run_pyct
from tests.acceptance.test_run_a_target_in_a_throwaway_process import (
    is_running,
    pid_written_to,
    pyct_in_a_session,
)

C_HANG = "targets.isolate.c_hang::stall"
SLOW_INPUTS = "targets.load.slow_inputs::f"
SLOW_IMPORT = "targets.load.slow_import::f"
COUNTER = "targets.isolate.counter::count"
CRASHES = "targets.load.crashes_at_import"
SEGFAULT = "targets.isolate.segfault::fault"
SWALLOWS_AT_IMPORT = "targets.load.swallows_stops_at_import::f"
SWALLOWS_IN_A_CALL = "targets.load.swallows_stops_in_a_call::f"
TELLS_ITS_PATH = "targets.load.tells_its_path::f"
HANGS_IN_C_AT_IMPORT = "targets.load.hangs_in_c_at_import::f"
# how soon a run whose target catches the stop must have ended: the stop's grace, and a margin
SWALLOWED_ENDED_WITHIN = STOP_GRACE + 1.5
# how soon after the signal every process of the run must have ended
ENDED_WITHIN = 1.5


def group_ended(group: int, within: float = 1.0) -> bool:
    """Whether no process of ``group`` is left ``within`` seconds, as the system reaps them.

    The system refuses to signal a group whose only processes are still
    exiting, so a refusal means to look again.
    """
    deadline = time.monotonic() + within
    while time.monotonic() < deadline:
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


# a SIGINT sent to the pid the shell got alone, as a harness sends one, stops an import
def test_a_sigint_to_pyct_alone_ends_an_import_as_a_ctrl_c_does(tmp_path: Path) -> None:
    pid_file = tmp_path / "pid"
    with pyct_in_a_session(SLOW_IMPORT, pid_file) as process:
        importing = pid_written_to(pid_file, process)
        sent = time.monotonic()
        os.kill(process.pid, signal.SIGINT)
        _, stderr = process.communicate(timeout=10)
        took = time.monotonic() - sent

        assert process.returncode == -signal.SIGINT, stderr
        assert stderr.splitlines()[-1] == "KeyboardInterrupt"
        assert "cannot import" not in stderr
        assert took < ENDED_WITHIN, took
        assert not is_running(importing)


# a Ctrl-C from the terminal reaches every process of the run once, not twice
def test_a_ctrl_c_during_an_import_ends_pyct_once(tmp_path: Path) -> None:
    pid_file = tmp_path / "pid"
    with pyct_in_a_session(SLOW_IMPORT, pid_file) as process:
        pid_written_to(pid_file, process)
        os.killpg(process.pid, signal.SIGINT)
        _, stderr = process.communicate(timeout=10)

        assert process.returncode == -signal.SIGINT, stderr
        assert stderr.count("Traceback (most recent call last)") == 1, stderr
        assert "cannot import" not in stderr


# a sitecustomize that starts a thread, as a host's instrumentation does
THREAD_AT_ENTRY = (
    "import threading, time\n"
    "threading.Thread(target=time.sleep, args=(3600,), daemon=True).start()\n"
)


def site_in(site: Path, *, thread: bool) -> dict[str, str]:
    """An environment whose interpreter runs ``site``'s sitecustomize before pyct runs.

    It starts a thread when ``thread`` says so, and does nothing otherwise.
    Python's warnings are on, so a fork of a threaded process would say so.
    """
    site.mkdir(exist_ok=True)
    (site / "sitecustomize.py").write_text(THREAD_AT_ENTRY if thread else "")
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONPATH"] = str(site)
    env["PYTHONWARNINGS"] = "default"
    return env


def run_in(env: dict[str, str], *argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-P", "-m", "pyct", "run", *argv],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def with_a_thread_at_entry(tmp_path: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    """``pyct run`` in an interpreter that starts a thread before pyct runs."""
    return run_in(site_in(tmp_path, thread=True), *argv)


# a process that runs other threads is never forked: pyct's process starts fresh instead
def test_a_thread_at_entry_forks_nothing(tmp_path: Path) -> None:
    result = with_a_thread_at_entry(tmp_path, COUNTER, '{"x": 0}')

    assert result.returncode == 0, result.stderr
    assert len(input_lines(result.stdout)) == 2, result.stdout
    assert "multi-threaded" not in result.stderr
    # pyct's own process runs the host's thread too, so its inputs start fresh, as they did
    assert (
        "each input runs in a fresh interpreter, because pyct's process runs other threads"
        in result.stderr
    )


# pyct's process started fresh is still watched through its import
def test_a_thread_at_entry_still_names_a_crash_at_import(tmp_path: Path) -> None:
    result = with_a_thread_at_entry(tmp_path, f"{CRASHES}::f", '{"x": 1}')

    assert result.stderr.splitlines() == [f"cannot import {CRASHES}: killed by SIGSEGV"]
    assert result.stdout == ""
    assert result.returncode == 1


# a crash that ends pyct's process after the import: the watcher says so and does not crash
def test_a_crash_after_the_import_is_said_and_not_repeated() -> None:
    result = run_pyct(SEGFAULT, '{"x": 7, "y": 0}', "--in-process")

    # the exit a shell gives a process SIGSEGV ends, from a watcher that exits instead
    assert result.returncode == 128 + signal.SIGSEGV
    assert result.stderr.splitlines()[-1] == "pyct's process was killed by SIGSEGV"


@contextmanager
def in_a_session(
    pid_file: Path, *argv: str, env: dict[str, str] | None = None
) -> Generator[subprocess.Popen[str]]:
    """``pyct run *argv`` in a session of its own, asked to write its target's pid to ``pid_file``.

    ``env`` is the environment, this one's without PYTHONPATH when not given.
    Whatever is left of the run is killed on the way out.
    """
    env = dict(env or {k: v for k, v in os.environ.items() if k != "PYTHONPATH"})
    env["PYCT_TEST_PID_FILE"] = str(pid_file)
    process = subprocess.Popen(
        [sys.executable, "-P", "-m", "pyct", "run", *argv],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        start_new_session=True,
    )
    try:
        yield process
    finally:
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)


# target code that catches BaseException catches the stop, and the run still ends
@pytest.mark.parametrize(
    "argv",
    [
        pytest.param((SWALLOWS_AT_IMPORT, '{"x": 0}'), id="at-import"),
        pytest.param((SWALLOWS_IN_A_CALL, '{"x": 0}', "--in-process"), id="in-a-call"),
    ],
)
def test_a_sigterm_ends_a_run_whose_target_catches_the_stop(
    argv: tuple[str, ...], tmp_path: Path
) -> None:
    pid_file = tmp_path / "pid"
    with in_a_session(pid_file, *argv) as process:
        pid_written_to(pid_file, process)
        sent = time.monotonic()
        os.kill(process.pid, signal.SIGTERM)
        process.wait(timeout=10)
        took = time.monotonic() - sent

        assert process.returncode == -signal.SIGTERM
        assert took < SWALLOWED_ENDED_WITHIN, took
        assert group_ended(process.pid)


def test_a_sigkill_to_pyct_ends_an_import_that_catches_the_stop(tmp_path: Path) -> None:
    pid_file = tmp_path / "pid"
    with in_a_session(pid_file, SWALLOWS_AT_IMPORT, '{"x": 0}') as process:
        importing = pid_written_to(pid_file, process)
        os.kill(process.pid, signal.SIGKILL)
        process.wait(timeout=10)

        assert group_ended(process.pid, within=SWALLOWED_ENDED_WITHIN)
        assert not is_running(importing)


# pyct's process started fresh gives the target the import path a forked one gives it
def test_a_fresh_pyct_process_gives_the_target_the_path_a_forked_one_does(
    tmp_path: Path,
) -> None:
    paths: dict[bool, object] = {}
    for thread in (False, True):
        env = site_in(tmp_path / "site", thread=thread)
        told = tmp_path / f"path-{thread}"
        env["PYCT_TEST_PATH"] = str(told)

        result = run_in(env, TELLS_ITS_PATH, '{"x": 0}')

        assert result.returncode == 0, result.stderr
        paths[thread] = json.loads(told.read_text())
    assert paths[True] == paths[False]


# pyct's process started fresh gets the lifeline too: killing the watcher ends it and its input
def test_a_sigkill_to_pyct_ends_a_fresh_pyct_process_and_its_input(tmp_path: Path) -> None:
    pid_file = tmp_path / "pid"
    env = site_in(tmp_path / "site", thread=True)
    with in_a_session(pid_file, C_HANG, '{"x": 0}', env=env) as process:
        child = pid_written_to(pid_file, process)
        os.kill(process.pid, signal.SIGKILL)
        process.wait(timeout=10)

        assert not is_running(child)
        assert group_ended(process.pid)


# pyct's process in one long C call runs no Python handler, and still ends on a SIGTERM
@pytest.mark.parametrize(
    "argv",
    [
        pytest.param((HANGS_IN_C_AT_IMPORT, '{"x": 0}'), id="at-import"),
        pytest.param((C_HANG, '{"x": 0}', "--in-process"), id="in-a-call"),
    ],
)
def test_a_sigterm_ends_pyct_s_process_in_c_code(argv: tuple[str, ...], tmp_path: Path) -> None:
    pid_file = tmp_path / "pid"
    with in_a_session(pid_file, *argv) as process:
        pid_written_to(pid_file, process)
        sent = time.monotonic()
        os.kill(process.pid, signal.SIGTERM)
        process.wait(timeout=10)
        took = time.monotonic() - sent

        assert process.returncode == -signal.SIGTERM
        assert took < SWALLOWED_ENDED_WITHIN, took
        assert group_ended(process.pid)


# the watcher killed while pyct's process is in one long C call: that process ends too
def test_a_sigkill_to_pyct_ends_its_process_in_c_code(tmp_path: Path) -> None:
    pid_file = tmp_path / "pid"
    with in_a_session(pid_file, HANGS_IN_C_AT_IMPORT, '{"x": 0}') as process:
        importing = pid_written_to(pid_file, process)
        os.kill(process.pid, signal.SIGKILL)
        process.wait(timeout=10)

        assert group_ended(process.pid, within=SWALLOWED_ENDED_WITHIN)
        assert not is_running(importing)

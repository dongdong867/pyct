"""One side's command: run in a process group of its own, stopped whole at its deadline."""

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from tools.compare_coverage import process
from tools.compare_coverage.process import (
    Command,
    Finished,
    StoppedError,
    allow_commands,
    run_command,
    side_environment,
    stop_every_command,
)

PYTHON = sys.executable


def command(tmp_path: Path, *argv: str) -> Command:
    return Command(argv=argv, cwd=tmp_path, environment=dict(os.environ))


def gone(pid: int) -> bool:
    """True once ``pid`` no longer runs. A killed orphan is reaped by init, not by us."""
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    return False


def test_a_command_that_ends_gives_its_exit_code_and_output(tmp_path: Path) -> None:
    script = "import os, sys; print(os.getcwd()); print('said', file=sys.stderr); sys.exit(3)"

    finished = run_command(command(tmp_path, PYTHON, "-c", script), wait=30)

    assert finished.returncode == 3
    assert finished.stdout == f"{tmp_path.resolve()}\n"
    assert finished.stderr == "said\n"
    assert finished.stopped_after is None


def test_a_command_gives_how_long_it_ran(tmp_path: Path) -> None:
    finished = run_command(command(tmp_path, PYTHON, "-c", "import time; time.sleep(0.3)"), 30)

    assert finished.seconds is not None
    assert 0.3 <= finished.seconds < 30


def test_output_that_is_not_utf8_is_read_with_replacements(tmp_path: Path) -> None:
    script = "import sys; sys.stdout.buffer.write(b'a\\xffb')"

    finished = run_command(command(tmp_path, PYTHON, "-c", script), wait=30)

    assert finished.stdout == "a�b"


def test_a_command_past_its_wait_is_stopped_with_everything_it_started(tmp_path: Path) -> None:
    # the command starts a process of its own, as legacy's engine and cvc5 do
    script = (
        "import subprocess, sys, time\n"
        "child = subprocess.Popen(['sleep', '60'])\n"
        "print(child.pid, flush=True)\n"
        "time.sleep(60)\n"
    )

    finished = run_command(command(tmp_path, PYTHON, "-c", script), wait=1)

    assert finished.returncode is None
    assert finished.stopped_after == 1
    assert finished.seconds is not None and finished.seconds >= 1
    assert gone(int(finished.stdout.split()[0]))


def test_what_a_command_left_running_is_stopped_when_it_ends(tmp_path: Path) -> None:
    # the child lets go of every stream, so nothing but the group ties it to the command
    script = "sleep 60 >/dev/null 2>&1 </dev/null & echo $!"

    finished = run_command(command(tmp_path, "/bin/sh", "-c", script), wait=30)

    assert (finished.returncode, finished.stopped_after) == (0, None)
    assert gone(int(finished.stdout))


def test_a_child_that_keeps_the_output_open_does_not_hold_up_the_command(
    tmp_path: Path,
) -> None:
    started = time.monotonic()

    finished = run_command(command(tmp_path, "/bin/sh", "-c", "sleep 60 & echo $!"), wait=30)

    assert (finished.returncode, finished.stopped_after) == (0, None)
    assert time.monotonic() - started < 10
    assert gone(int(finished.stdout))


def test_an_interrupted_wait_stops_the_command_and_goes_on_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started: list[subprocess.Popen[bytes]] = []
    real_init = subprocess.Popen.__init__

    def remember(self: subprocess.Popen[bytes], *args: object, **kwargs: object) -> None:
        real_init(self, *args, **kwargs)  # type: ignore[arg-type]
        started.append(self)

    real_wait = subprocess.Popen.wait
    waits: list[float | None] = []

    def interrupted(self: subprocess.Popen[bytes], timeout: float | None = None) -> int:
        # Ctrl-C lands in the first wait, the one for the command to end
        waits.append(timeout)
        if len(waits) == 1:
            raise KeyboardInterrupt
        return real_wait(self, timeout)

    monkeypatch.setattr(subprocess.Popen, "__init__", remember)
    monkeypatch.setattr(subprocess.Popen, "wait", interrupted)

    with pytest.raises(KeyboardInterrupt):
        run_command(command(tmp_path, "sleep", "60"), wait=30)

    assert started[0].wait(timeout=5) == -signal.SIGKILL


def test_a_side_runs_without_pythonpath_or_coverage_startup() -> None:
    base = {
        "PATH": "/bin",
        "PYTHONPATH": "/elsewhere",
        "COVERAGE_PROCESS_START": "x",
        "COVERAGE_PROCESS_CONFIG": "y",
        "COVERAGE_FILE": "kept",
    }

    assert side_environment(base) == {"PATH": "/bin", "COVERAGE_FILE": "kept"}


def sleeping_in_a_thread(tmp_path: Path) -> tuple[threading.Thread, list[Finished]]:
    """A thread waiting on a long command, once the command runs, and where it puts its end."""
    finished: list[Finished] = []
    waiter = threading.Thread(
        target=lambda: finished.append(run_command(command(tmp_path, "sleep", "60"), wait=60))
    )
    waiter.start()
    deadline = time.monotonic() + 10
    while not process._RUNNING:
        assert time.monotonic() < deadline, "the command never started"
        time.sleep(0.05)
    return waiter, finished


def test_stopping_every_command_ends_one_another_thread_waits_on_and_refuses_more(
    tmp_path: Path,
) -> None:
    started = time.monotonic()
    waiter, finished = sleeping_in_a_thread(tmp_path)

    try:
        stop_every_command()
        waiter.join(timeout=10)
        with pytest.raises(StoppedError):
            run_command(command(tmp_path, "true"), wait=5)
    finally:
        allow_commands()

    assert finished[0].returncode == -signal.SIGKILL
    assert time.monotonic() - started < 10
    assert run_command(command(tmp_path, "true"), wait=5).returncode == 0


def test_a_group_the_system_refuses_to_signal_does_not_stop_the_others(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # macOS refuses to signal a group whose every member exited and is not yet reaped
    ended = subprocess.Popen(["true"], start_new_session=True)
    ended.wait()
    real_killpg = os.killpg

    def killpg(pid: int, sig: int) -> None:
        if pid == ended.pid:
            raise PermissionError(1, "Operation not permitted")
        real_killpg(pid, sig)

    monkeypatch.setattr(process.os, "killpg", killpg)
    waiter, finished = sleeping_in_a_thread(tmp_path)
    process._RUNNING.add(ended)

    try:
        stop_every_command()
        waiter.join(timeout=10)
    finally:
        process._RUNNING.discard(ended)
        allow_commands()

    assert finished[0].returncode == -signal.SIGKILL

"""Run one side's command in a process group of its own, and stop the whole group when it ends.

A side starts processes of its own: legacy's engine runs the target in a spawned child, and
both sides start cvc5. The command leads a new session, so its process group holds all of
them. The group is killed once the command ends, whether it exited, ran past its deadline or
was interrupted, so nothing it started keeps the machine busy while the next side runs.

Output goes to temporary files rather than pipes: a process the command left behind that
still holds its output can then never keep the checker waiting after the command exited.

Rows that run at once wait on their commands in threads of their own, where Ctrl-C does not
land. ``stop_every_command`` stops the group of every command still running and refuses to
start another, until ``allow_commands``; a command starts and is counted as running at once,
so none can start unseen between the two.
"""

import contextlib
import os
import signal
import subprocess
import tempfile
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import IO

# a side measures its own lines: PYTHONPATH could put other modules first, and coverage.py's
# startup variables would start a second tracer inside the side
LEFT_OUT_OF_A_SIDE = ("PYTHONPATH", "COVERAGE_PROCESS_START", "COVERAGE_PROCESS_CONFIG")


# the commands started and not yet ended, and whether a new one may start
_LOCK = threading.Lock()
_RUNNING: set[subprocess.Popen[bytes]] = set()
_STOPPING = threading.Event()


class StoppedError(Exception):
    """A command was not started: the run is stopping every command it started."""


@dataclass(frozen=True)
class Command:
    """What to run, where, and with what environment."""

    argv: tuple[str, ...]
    cwd: Path
    environment: Mapping[str, str]


@dataclass(frozen=True)
class Finished:
    """How a command ended. ``returncode`` is ``None`` when it was stopped at its deadline."""

    returncode: int | None
    stdout: str
    stderr: str
    stopped_after: float | None = None


def side_environment(base: Mapping[str, str]) -> dict[str, str]:
    """The checker's own environment, less what would change what a side measures."""
    return {name: value for name, value in base.items() if name not in LEFT_OUT_OF_A_SIDE}


def run_command(command: Command, wait: float) -> Finished:
    """Run ``command`` to its end or for ``wait`` seconds, then stop its whole process group."""
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        process = _start(command, out, err)
        stopped_after = None
        try:
            process.wait(timeout=wait)
        except subprocess.TimeoutExpired:
            stopped_after = wait
        finally:
            with _LOCK:
                _RUNNING.discard(process)
            _stop(process)
        process.wait()
        returncode = None if stopped_after is not None else process.returncode
        return Finished(returncode, _text(out), _text(err), stopped_after)


def stop_every_command() -> None:
    """Stop the group of every command still running, and start no other until allowed."""
    with _LOCK:
        _STOPPING.set()
        for process in _RUNNING:
            _stop(process)


def allow_commands() -> None:
    """Let commands start again after ``stop_every_command``."""
    _STOPPING.clear()


def _start(command: Command, out: IO[bytes], err: IO[bytes]) -> subprocess.Popen[bytes]:
    """Start ``command`` and count it as running, unless every command is being stopped."""
    with _LOCK:
        if _STOPPING.is_set():
            raise StoppedError(f"not started, the run is stopping: {command.argv[0]}")
        process = subprocess.Popen(
            command.argv,
            cwd=command.cwd,
            env=dict(command.environment),
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=err,
            start_new_session=True,
        )
        _RUNNING.add(process)
        return process


def _text(file: IO[bytes]) -> str:
    """All a command wrote to ``file``, read as UTF-8 with anything else replaced."""
    file.seek(0)
    return file.read().decode("utf-8", errors="replace")


def _stop(process: subprocess.Popen[bytes]) -> None:
    """Kill the command's whole process group. A group already gone needs nothing.

    The group keeps its id while any member runs, so no other process can hold that id then.
    """
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGKILL)

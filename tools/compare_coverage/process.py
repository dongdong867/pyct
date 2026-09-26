"""Run one side's command in a process group of its own, and stop the group at its deadline.

A side starts processes of its own: legacy's engine runs the target in a spawned child, and
both sides start cvc5. The command leads a new session, so its process group holds all of
them, and a side stopped at its deadline or by Ctrl-C is stopped whole. Nothing a side
started outlives its row.
"""

import contextlib
import os
import signal
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

# a side measures its own lines: PYTHONPATH could put other modules first, and coverage.py's
# startup variables would start a second tracer inside the side
LEFT_OUT_OF_A_SIDE = ("PYTHONPATH", "COVERAGE_PROCESS_START", "COVERAGE_PROCESS_CONFIG")


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
    """Run ``command`` to its end, or stop its whole process group after ``wait`` seconds."""
    process = subprocess.Popen(
        command.argv,
        cwd=command.cwd,
        env=dict(command.environment),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=wait)
    except subprocess.TimeoutExpired:
        _stop(process)
        stdout, stderr = process.communicate()
        return Finished(returncode=None, stdout=stdout, stderr=stderr, stopped_after=wait)
    except BaseException:
        _stop(process)
        raise
    return Finished(returncode=process.returncode, stdout=stdout, stderr=stderr)


def _stop(process: subprocess.Popen[str]) -> None:
    """Kill the command's whole process group. A group already gone needs nothing."""
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGKILL)

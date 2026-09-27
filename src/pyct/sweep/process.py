"""The processes a sweep starts: one command waited for with a limit, a group stop, and the
SIGHUP that must not leave either behind.

Each command sweep starts leads a session of its own, so its process group
holds every process it started in turn, and the whole group is killed once
sweep is done with it, as the compare tool learned. A command's output goes
to temporary files rather than pipes: a process the command left holding a
pipe could keep sweep waiting, and a file never fills up and blocks the
command. This code stays in pyct, beside the compare tool's own runner,
since neither may import the other (sweep-keeps-its-own-process-runner).
"""

import contextlib
import os
import signal
import subprocess
import tempfile
from collections.abc import Generator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO

from pyct.run.process import Waited


@dataclass(frozen=True)
class Finished:
    """How a command ended, or None when it still ran at its limit, and what it wrote."""

    waited: Waited | None
    stdout: str
    stderr: str


class _HangUpError(BaseException):
    """A SIGHUP, raised so what sweep started is stopped before sweep ends by it."""


def run_command(
    argv: Sequence[str], *, cwd: Path, env: Mapping[str, str], limit: float
) -> Finished:
    """Run ``argv`` in ``cwd`` with ``env``, wait at most ``limit`` seconds, and stop its group.

    A Ctrl-C, the ``Stopped`` a SIGTERM raises in the command's process (see
    ``pyct.run.launch``), or a SIGHUP under ``hangup_stops_children`` stops
    the group on its way out.
    """
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        process = subprocess.Popen(
            argv,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=err,
            start_new_session=True,
        )
        try:
            waited = _waited(process, limit)
        finally:
            stop_group(process)
        return Finished(waited, _read(out), _read(err))


def _waited(process: subprocess.Popen[bytes], limit: float) -> Waited | None:
    try:
        return waited_of(process.wait(timeout=limit))
    except subprocess.TimeoutExpired:
        return None


def waited_of(returncode: int) -> Waited:
    """A ``Popen`` return code as the ``Waited`` that ``pyct.run.process.how`` words."""
    if returncode < 0:
        return Waited(signal=-returncode, code=None)
    return Waited(signal=None, code=returncode)


def _read(file: IO[bytes]) -> str:
    file.seek(0)
    return file.read().decode("utf-8", errors="replace")


def stop_group(process: subprocess.Popen[bytes]) -> None:
    """Kill the process's whole group and reap the process.

    A group with no process left needs nothing; on macOS a group whose only
    member has exited but is not yet reaped refuses the signal.
    """
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(process.pid, signal.SIGKILL)
    process.wait()


@contextlib.contextmanager
def hangup_stops_children() -> Generator[None]:
    """Stop what sweep started before a SIGHUP ends sweep, then put the old handler back.

    Each process sweep starts leads a session of its own, so the SIGHUP a
    closing terminal sends never reaches it, and ending sweep by the
    SIGHUP's default action would leave it running, forever if an import
    hangs. So the SIGHUP raises inside the block, the ``finally`` that stops
    the process's group runs, and the sweep then ends by the SIGHUP itself.
    A SIGHUP already ignored, as ``nohup`` ignores it, stays so. A SIGTERM
    needs nothing here: the command's process raises ``Stopped`` for it,
    which the same ``finally`` meets. Like a Ctrl-C's handling, this needs
    the main thread.
    """
    previous = signal.getsignal(signal.SIGHUP)
    if previous is signal.SIG_DFL:
        signal.signal(signal.SIGHUP, _hang_up)
    try:
        yield
    except _HangUpError:
        signal.signal(signal.SIGHUP, signal.SIG_DFL)
        signal.raise_signal(signal.SIGHUP)
        raise
    finally:
        signal.signal(signal.SIGHUP, signal.SIG_DFL if previous is None else previous)


def _hang_up(number: int, frame: object) -> None:
    """Raise so what sweep started is stopped. A closing terminal can send a second SIGHUP,
    which is ignored from here on so it cannot cut that short; the sweep then ends by the
    SIGHUP."""
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    raise _HangUpError

"""``pyct run`` measured from launch to exit, from outside: wall time, CPU time and peak memory.

The criteria that bound a run's time bound its wall time from launch. A slow moment of a loaded
machine can stretch one run past such a bound, so ``within`` runs again, up to ``TRIES`` runs,
and hands back the first that fits, or the last: a run that is always late still fails.
"""

import contextlib
import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.acceptance.harness import COVERAGE_STARTUP, REPO_ROOT

# how often the test looks for the starter's end
_POLL = 0.01

# Starts pyct, waits for it and writes what it used: its exit status, its wall time from launch
# to exit, and the CPU time and peak memory of pyct's process and of every process it waited
# for. A small interpreter of its own starts pyct, since a process's peak memory on Linux
# starts at the peak of the process that started it, and keeps it across exec: started from a
# pytest worker, pyct would report the worker's. SIGPIPE and SIGXFSZ start at their defaults,
# as subprocess starts them.
_STARTER = """\
import os, signal, sys, time
used, argv = sys.argv[1], sys.argv[2:]
start = time.monotonic()
pid = os.posix_spawn(argv[0], argv, os.environ, setsigdef=(signal.SIGPIPE, signal.SIGXFSZ))
with open(used + ".pid", "w") as file:
    file.write(str(pid))
_, status, usage = os.wait4(pid, 0)
wall = time.monotonic() - start
with open(used, "w") as file:
    file.write(f"{status} {wall!r} {usage.ru_utime + usage.ru_stime!r} {usage.ru_maxrss}")
"""

# the runs a wall bound gets before a test fails
TRIES = 3


@dataclass(frozen=True)
class Measured:
    """What one run printed, how it exited, and what it cost."""

    stdout: str
    stderr: str
    returncode: int
    wall: float
    cpu: float
    peak_bytes: int


def measured(tmp_path: Path, argv: Sequence[str], *, timeout: float = 45) -> Measured:
    """Run ``pyct run`` with ``argv`` from the repository root, from launch to exit.

    Like the harness, it leaves coverage.py out, since every run here has a
    budget. ``_STARTER`` starts pyct and reads, as ``/usr/bin/time`` does, the
    resource use of pyct's process and of every process it waited for, each
    input's and each cvc5's: the CPU time is their sum, and the peak memory
    their largest.
    """
    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", *COVERAGE_STARTUP}}
    out, err, used = tmp_path / "out", tmp_path / "err", tmp_path / "used"
    for left in (used, Path(f"{used}.pid")):
        left.unlink(missing_ok=True)
    with out.open("w") as stdout, err.open("w") as stderr:
        starter = subprocess.Popen(
            [sys.executable, "-I", "-S", "-c", _STARTER, str(used)]
            + [sys.executable, "-P", "-m", "pyct", "run", *argv],
            cwd=REPO_ROOT,
            env=env,
            stdout=stdout,
            stderr=stderr,
        )
        _waited(starter, used, time.monotonic() + timeout)
    status, wall, cpu, peak = used.read_text().split()
    # macOS counts the peak in bytes, Linux in KiB
    unit = 1 if sys.platform == "darwin" else 1024
    return Measured(
        out.read_text(),
        err.read_text(),
        os.waitstatus_to_exitcode(int(status)),
        float(wall),
        float(cpu),
        int(peak) * unit,
    )


def within(tmp_path: Path, argv: Sequence[str], fits: Callable[[Measured], bool]) -> Measured:
    """The first of up to ``TRIES`` runs that ``fits``, or the last run."""
    for _ in range(TRIES - 1):
        run = measured(tmp_path, argv)
        if fits(run):
            return run
    return measured(tmp_path, argv)


def _waited(starter: subprocess.Popen[bytes], used: Path, until: float) -> None:
    """Wait for ``starter`` to write what pyct used to ``used``, or fail the test at ``until``,
    once pyct and the starter are killed."""
    while time.monotonic() < until:
        if starter.poll() is not None:
            assert used.exists(), f"the starter ended with {starter.returncode} and no measure"
            return
        time.sleep(_POLL)
    with contextlib.suppress(FileNotFoundError, ProcessLookupError):
        os.kill(int(Path(f"{used}.pid").read_text()), signal.SIGKILL)
    starter.kill()
    starter.wait()
    pytest.fail("pyct ran past the test's own limit")

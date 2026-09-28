"""``pyct run`` measured from launch to exit, from outside: wall time, CPU time and peak memory.

The criteria that bound a run's time bound its wall time from launch. A slow moment of a loaded
machine can stretch one run past such a bound, so ``within`` runs again, up to ``TRIES`` runs,
and hands back the first that fits, or the last: a run that is always late still fails.
"""

import os
import resource
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.acceptance.harness import COVERAGE_STARTUP, REPO_ROOT

# how often the wait looks at the child, which bounds what the wall time overstates
_POLL = 0.01

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
    budget. The wait reads the resource use of pyct's process and of every
    process it waited for, each input's and each cvc5's, as ``/usr/bin/time``
    does: the CPU time is their sum, and the peak memory their largest.
    """
    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", *COVERAGE_STARTUP}}
    out, err = tmp_path / "out", tmp_path / "err"
    with out.open("w") as stdout, err.open("w") as stderr:
        start = time.monotonic()
        child = subprocess.Popen(
            [sys.executable, "-P", "-m", "pyct", "run", *argv],
            cwd=REPO_ROOT,
            env=env,
            stdout=stdout,
            stderr=stderr,
        )
        status, usage = _waited(child, start + timeout)
        wall = time.monotonic() - start
    # macOS counts the peak in bytes, Linux in KiB
    unit = 1 if sys.platform == "darwin" else 1024
    return Measured(
        out.read_text(),
        err.read_text(),
        os.waitstatus_to_exitcode(status),
        wall,
        usage.ru_utime + usage.ru_stime,
        usage.ru_maxrss * unit,
    )


def within(tmp_path: Path, argv: Sequence[str], fits: Callable[[Measured], bool]) -> Measured:
    """The first of up to ``TRIES`` runs that ``fits``, or the last run."""
    for _ in range(TRIES - 1):
        run = measured(tmp_path, argv)
        if fits(run):
            return run
    return measured(tmp_path, argv)


def _waited(child: subprocess.Popen[bytes], until: float) -> tuple[int, resource.struct_rusage]:
    """The child's exit status and resource use, or a failed test when it outlives ``until``."""
    while time.monotonic() < until:
        pid, status, usage = os.wait4(child.pid, os.WNOHANG)
        if pid:
            child.returncode = os.waitstatus_to_exitcode(status)
            return status, usage
        time.sleep(_POLL)
    child.kill()
    child.wait()
    pytest.fail("pyct ran past the test's own limit")

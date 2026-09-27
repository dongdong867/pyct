"""One entry's ``pyct run``: its command, a temporary directory of its own, and its row.

Each entry runs as the ``pyct run`` a person would type, with the same flags,
in a process of its own (sweep-runs-each-entry-as-pyct-run), so a crash, an
exit, or a hang costs that entry's row and nothing else.

It starts in a fresh, empty temporary directory that is deleted once its row
is known (sweep-runs-each-entry-in-a-temporary-directory). Sweep calls every
entry with inputs it made up, so a file an entry writes by a relative path
lands there instead of the person's project, and no entry sees another's
files. The directory does not catch a write to any other path or a request
an input sends. ``pyct run`` puts its working directory, the empty one,
first on the path, so sweep's own working directory goes at the front of
``PYTHONPATH``: the entry's module still imports from the file the listing
found. The run otherwise gets the environment sweep got.
"""

import json
import os
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

from pyct.run.process import how
from pyct.sweep.process import Finished, run_command
from pyct.sweep.result import SweepLimits
from pyct.sweep.rows import Row, Status

# pyct, started with sweep's own interpreter, so each run has sweep's Python; -P keeps a folder
# named pyct in the entry's working directory from standing in for pyct
PYCT: tuple[str, ...] = (sys.executable, "-P", "-m", "pyct")


def run_entry(row: Row, limits: SweepLimits, *, budget: float, pyct: tuple[str, ...] = PYCT) -> Row:
    """Run a listed entry with its seed, a budget of ``budget`` seconds, and ``limits``' plateau
    and solver timeout.

    The row is ``ran`` when its run exits 0 and prints its summary line, and
    ``failed`` otherwise, keeping the summary line when there was one. A run
    still going ``limits.grace`` seconds past its budget is stopped with
    every process it started.
    """
    argv = [*pyct, "run", f"{row.module}::{row.name}", "--args", json.dumps(row.seed)]
    argv += ["--budget", repr(budget), "--plateau", str(limits.plateau)]
    argv += ["--solver-timeout", repr(limits.solver_timeout)]
    with tempfile.TemporaryDirectory(prefix="pyct-sweep-") as directory:
        limit = budget + limits.grace
        finished = run_command(argv, cwd=Path(directory), env=_environment(), limit=limit)
    return _outcome(row, finished, limits.grace)


def _environment() -> dict[str, str]:
    """Sweep's environment, with its working directory at the front of ``PYTHONPATH``."""
    here = os.getcwd()
    path = os.environ.get("PYTHONPATH")
    return {**os.environ, "PYTHONPATH": os.pathsep.join([here, path]) if path else here}


def _outcome(row: Row, finished: Finished, grace: float) -> Row:
    """The row a finished run makes."""
    summary = _summary(finished.stdout)
    waited = finished.waited
    if waited is None:
        reason = f"stopped {grace:g} s past its budget"
    elif waited.signal is not None:
        reason = how(waited)
    elif waited.code == 0 and summary is not None:
        return replace(row, status=Status.RAN, run=summary)
    else:
        reason = f"exit {waited.code}: {_last_line(finished.stderr)}"
    return replace(row, status=Status.FAILED, reason=reason, run=summary)


def _summary(stdout: str) -> Mapping[str, object] | None:
    """The last stdout line that carries ``stopped``: the summary line ``pyct run`` prints last.

    No input's line carries ``stopped``. A line a killed run cut short is no line.
    """
    for line in reversed(stdout.splitlines()):
        try:
            read = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(read, dict) and "stopped" in read:
            return read
    return None


def _last_line(stderr: str) -> str:
    """The last line with text that the run wrote to stderr, or nothing."""
    lines = [line for line in stderr.splitlines() if line.strip()]
    return lines[-1] if lines else ""

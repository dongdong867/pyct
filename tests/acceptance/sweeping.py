"""What the sweep acceptance tests share: spawn ``pyct sweep`` and read its lines.

Each spawns ``python -P -m pyct sweep ...`` from the repository root unless told otherwise, so
each fixture package under ``targets/sweep/`` is named from ``targets``. stdout is one JSON
line per row, then the summary line, which a tool tells from a row by ``swept``.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from tests.acceptance.harness import COVERAGE_STARTUP, REPO_ROOT

FIXTURES = "targets.sweep"

# the command a person types, started with this interpreter
SWEEP = (sys.executable, "-P", "-m", "pyct", "sweep")


def sweep(
    *argv: str,
    env: dict[str, str] | None = None,
    timeout: float = 60,
    cwd: Path = REPO_ROOT,
    measured: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Spawn ``pyct sweep`` with ``argv``. ``env`` adds to or replaces the child's variables.

    ``measured=False`` leaves coverage.py out of the sweep and every process it starts: an
    entry's run whose deadline fires inside coverage.py's tracer hangs, as ``run_pyct`` says.
    """
    return subprocess.run(
        [*SWEEP, *argv],
        cwd=cwd,
        env=environment(env, measured=measured),
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def environment(env: dict[str, str] | None = None, *, measured: bool = True) -> dict[str, str]:
    """This process's variables without ``PYTHONPATH``, and without coverage.py's unless
    ``measured``, with ``env`` added or replacing."""
    unset = {"PYTHONPATH", *(() if measured else COVERAGE_STARTUP)}
    child = {name: value for name, value in os.environ.items() if name not in unset}
    child.update(env or {})
    return child


def rows(stdout: str) -> list[dict[str, Any]]:
    """The rows, without the summary line that closes stdout."""
    lines = [json.loads(line) for line in stdout.splitlines()]
    assert lines and "swept" in lines[-1], stdout
    return lines[:-1]


def summary(stdout: str) -> dict[str, Any]:
    return json.loads(stdout.splitlines()[-1])


def row_named(stdout: str, module: str, name: str | None) -> dict[str, Any]:
    found = [row for row in rows(stdout) if row["module"] == module and row["name"] == name]
    assert len(found) == 1, stdout
    return found[0]


def names(stdout: str) -> list[object]:
    return [row["name"] for row in rows(stdout)]

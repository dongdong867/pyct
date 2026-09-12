"""What every acceptance test needs: spawn pyct, run it in process, read its stdout.

The subprocess runs ``python -P -m pyct`` from the repository root with
``PYTHONPATH`` removed, so a test proves the target imports from the working
directory rather than from an inherited path.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def run_pyct(*argv: str, path: str | None = None) -> subprocess.CompletedProcess[str]:
    """Spawn ``pyct run`` with the given argv. ``path`` replaces the child's ``PATH``."""
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    if path is not None:
        env["PATH"] = path
    return subprocess.run(
        [sys.executable, "-P", "-m", "pyct", "run", *argv],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        # the timeout test spawns a target that never returns, so a broken
        # budget has to fail the test instead of hanging the suite
        timeout=30,
    )


def let_pyct_run_in_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """Put this interpreter where a fresh one would be, and undo it after the test.

    ``load_target`` inserts the working directory on ``sys.path`` and leaves the
    imported target in ``sys.modules``; both are restored so the subprocess tests
    around this one keep proving what they prove.
    """
    monkeypatch.chdir(REPO_ROOT)
    monkeypatch.setattr(sys, "path", list(sys.path))
    for name in [n for n in sys.modules if n.split(".", 1)[0] == "targets"]:
        monkeypatch.delitem(sys.modules, name)


def one_line(stdout: str) -> dict[str, object]:
    lines = stdout.splitlines()
    assert len(lines) == 1, stdout
    return json.loads(lines[0])


def two_lines(stdout: str) -> tuple[dict[str, object], dict[str, object]]:
    lines = stdout.splitlines()
    assert len(lines) == 2, stdout
    return json.loads(lines[0]), json.loads(lines[1])

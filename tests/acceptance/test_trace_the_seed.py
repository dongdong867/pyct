"""Acceptance tests for the trace-the-seed story, child run-the-seed-and-print-the-line.

Every test spawns ``python -m pyct`` in a subprocess from the repository root with
``PYTHONPATH`` removed. The current-directory criterion cannot be proven in-process,
and the import-path edit ``load_target`` makes would leak between in-process tests.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TARGET = "targets.trace.uncalled_helper::classify"
TARGET_FILE = str(REPO_ROOT / "targets" / "trace" / "uncalled_helper.py")


def run_pyct(*argv: str) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    return subprocess.run(
        [sys.executable, "-m", "pyct", "run", *argv],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def one_line(stdout: str) -> dict[str, object]:
    lines = stdout.splitlines()
    assert len(lines) == 1, stdout
    return json.loads(lines[0])


# trace-the-seed-imports-from-the-current-directory
def test_imports_from_the_current_directory() -> None:
    result = run_pyct(TARGET, '{"x": 1}')

    assert result.returncode == 0, result.stderr
    line = one_line(result.stdout)
    assert line["args"] == {"x": 1}

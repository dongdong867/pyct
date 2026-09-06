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


# trace-the-seed-counts-lines-against-the-module
def test_counts_lines_against_the_module() -> None:
    result = run_pyct(TARGET, '{"x": 1}')

    line = one_line(result.stdout)
    # docstring, two def lines, four body lines; never_called's body is in the total
    assert line["total"] == {TARGET_FILE: 7}
    # only the two lines the seed ran: the if and its return
    assert line["covered"] == {TARGET_FILE: [5, 6]}


# trace-the-seed-refuses-missing-args
def test_refuses_missing_args() -> None:
    result = run_pyct(TARGET)

    assert result.returncode == 2
    assert result.stdout == ""
    assert "required" in result.stderr
    assert "x" in result.stderr.split("required", 1)[1]
    assert "--args" in result.stderr

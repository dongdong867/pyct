"""A test marked ``DEADLINE_FIRES`` runs with no coverage.py tracer, in one process or in workers.

A parallel run's worker runs two measurements, and a deadline that fires under either can
leave coverage.py's lock held, as ``tests/unit/deadline_fires.py`` says.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# a test that notes the trace function it runs under
MARKED_TEST = """
import sys

from tests.unit.deadline_fires import DEADLINE_FIRES


@DEADLINE_FIRES
def test_marked():
    assert sys.gettrace() is None, sys.gettrace()


def test_measured():
    assert sys.gettrace() is not None
"""


@pytest.mark.parametrize("workers", ["0", "1"])
def test_a_deadline_test_runs_untraced_under_coverage(tmp_path: Path, workers: str) -> None:
    (tmp_path / "test_marked.py").write_text(MARKED_TEST)
    # the child keeps its own data file, starts no coverage of this run, and finds this suite
    env = {k: v for k, v in os.environ.items() if not k.startswith("COVERAGE_")}
    env["COVERAGE_FILE"] = str(tmp_path / ".coverage")
    env["PYTHONPATH"] = str(REPO_ROOT)
    config = str(REPO_ROOT / "pyproject.toml")

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "test_marked.py", "-c", config, "--rootdir", str(tmp_path)]
        + ["--confcutdir", str(tmp_path), "-p", "tests.conftest", "-n", workers, "--cov"]
        + [f"--cov-config={config}", "--cov-report=", "--cov-fail-under=0"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=40,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "2 passed" in result.stdout, result.stdout

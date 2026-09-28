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


# a test whose deadline fires in the test process, with the mark and without it
FIRING_TESTS = """
import time

import pytest

from pyct.execution.deadline import DeadlineError, deadline
from tests.unit.deadline_fires import DEADLINE_FIRES


def fire():
    with pytest.raises(DeadlineError), deadline(time.monotonic()):
        time.sleep(1)


@DEADLINE_FIRES
def test_marked():
    fire()


def test_unmarked():
    fire()
"""


def test_a_deadline_that_fires_in_an_unmarked_test_fails_it(tmp_path: Path) -> None:
    (tmp_path / "test_firing.py").write_text(FIRING_TESTS)
    env = {k: v for k, v in os.environ.items() if not k.startswith("COVERAGE_")}
    env["PYTHONPATH"] = str(REPO_ROOT)
    config = str(REPO_ROOT / "pyproject.toml")

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "test_firing.py", "-c", config, "--rootdir", str(tmp_path)]
        + ["--confcutdir", str(tmp_path), "-p", "tests.conftest", "-p", "no:cacheprovider"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=40,
    )

    assert result.returncode == 1, result.stdout + result.stderr
    assert "test_firing.py::test_marked PASSED" in result.stdout, result.stdout
    assert "ERROR at teardown of test_unmarked" in result.stdout, result.stdout
    assert "fired its deadline in this process without DEADLINE_FIRES" in result.stdout

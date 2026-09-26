"""The per-test timeout in pyproject.toml ends a test stuck on coverage.py's data lock.

That lock is where a deadline firing under coverage leaves a run waiting forever, as
``tests/unit/deadline_fires.py`` says. The timeout is only a backstop if it ends that wait.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# a test that takes coverage.py's data lock, as the deadline leaves it, and waits
STUCK_TEST = """
import time

import coverage


def test_stuck_on_coverages_lock():
    coverage.Coverage.current()._collector.data_lock.acquire()
    time.sleep(3600)
"""


def test_the_timeout_ends_a_test_stuck_on_coverages_lock(tmp_path: Path) -> None:
    (tmp_path / "test_stuck.py").write_text(STUCK_TEST)
    # the child keeps its own data file, and starts no coverage of this run's
    env = {k: v for k, v in os.environ.items() if not k.startswith("COVERAGE_")}
    env["COVERAGE_FILE"] = str(tmp_path / ".coverage")
    config = str(REPO_ROOT / "pyproject.toml")
    started = time.monotonic()

    # the project's pytest and coverage settings, with the timeout cut to two seconds
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "test_stuck.py", "-c", config, "--rootdir", str(tmp_path)]
        + ["--cov", f"--cov-config={config}", "-o", "timeout=2"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 1, result.stdout
    assert "+ Timeout +" in result.stdout + result.stderr
    # two seconds of timeout, and the child's own start and stop
    assert time.monotonic() - started < 20

"""Acceptance tests for give-legacy-runs-their-own-temp-folder: legacy leaves nothing behind.

Legacy's line tracer leaves a ``.pyct-cov.*`` file in the temp folder for each input it runs.
Each test gives the checker a temp folder of its own, standing for the system's, and checks
that it is empty once legacy has run: every legacy process ran in a folder of its own under
it, and that folder is gone. The stub engine leaves such a file too, and says which temp
folder it saw, so the stub tests also show where legacy ran.
"""

import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from subprocess import PIPE

import pytest

from tests.compare_coverage.acceptance.checker import (
    ONE_CHECK,
    REPO_ROOT,
    checker_environment,
    legacy_side,
    run_checker,
)
from tests.compare_coverage.conftest import StubCheckout
from tools.compare_coverage.legacy_side import probe
from tools.compare_coverage.process import side_environment
from tools.compare_coverage.sides import Limits, SideRequest

# long enough for the v2 side to finish first and the stub to record its call
INTERRUPT_WAIT = 30.0


@pytest.fixture
def system(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A temp folder standing for the system's, for this process and every process it starts."""
    folder = tmp_path / "system"
    folder.mkdir()
    for name in ("TMPDIR", "TEMP", "TMP"):
        monkeypatch.setenv(name, str(folder))
    monkeypatch.setattr(tempfile, "tempdir", str(folder))
    return folder


def left_in(folder: Path) -> list[str]:
    return sorted(entry.name for entry in folder.iterdir())


def one_check(budget: float = 2.0) -> SideRequest:
    return SideRequest(ONE_CHECK, {"x": 0}, REPO_ROOT, Limits(budget=budget), wait=60)


def ran_in(stub_checkout: StubCheckout, system: Path) -> Path:
    """The temp folder the stub's one call saw: one of its own, inside ``system``."""
    [call] = stub_checkout.calls()
    folder = Path(call["temp"])
    assert folder.parent == system
    return folder


@pytest.mark.legacy
@pytest.mark.timeout(180)
def test_the_checker_leaves_nothing_in_the_temp_folder(
    legacy_checkout: Path, tmp_path: Path
) -> None:
    """give-legacy-runs-their-own-temp-folder-leaks-nothing-from-the-gate"""
    system = tmp_path / "system"
    system.mkdir()

    result = run_checker(
        "--legacy", str(legacy_checkout), "--target", ONE_CHECK, "--budget", "2", temp=system
    )

    assert result.returncode == 0, result.stderr
    assert left_in(system) == []


@pytest.mark.legacy
@pytest.mark.timeout(180)
def test_the_tests_legacy_side_leaves_nothing_in_the_temp_folder(
    legacy_checkout: Path, system: Path
) -> None:
    """give-legacy-runs-their-own-temp-folder-leaks-nothing-from-the-tests"""
    report = legacy_side(legacy_checkout).run(one_check())

    assert report.failure is None
    assert report.inputs
    assert left_in(system) == []


def test_a_run_that_ends_normally_removes_its_folder(
    stub_checkout: StubCheckout, system: Path
) -> None:
    """give-legacy-runs-their-own-temp-folder-removes-its-folder"""
    report = legacy_side(stub_checkout.path).run(one_check())

    assert report.failure is None
    assert not ran_in(stub_checkout, system).exists()
    assert left_in(system) == []


def test_a_run_that_fails_removes_its_folder(stub_checkout: StubCheckout, system: Path) -> None:
    """give-legacy-runs-their-own-temp-folder-removes-its-folder"""
    stub_checkout.script({ONE_CHECK: {"exit": 3, "say": "gone"}})

    report = legacy_side(stub_checkout.path).run(one_check())

    assert report.failure == "exit 3: gone"
    assert not ran_in(stub_checkout, system).exists()
    assert left_in(system) == []


def test_the_probe_removes_its_folder(stub_checkout: StubCheckout, system: Path) -> None:
    """give-legacy-runs-their-own-temp-folder-removes-its-folder"""
    python = stub_checkout.path / ".venv" / "bin" / "python"
    real = python.with_name("real-python")
    python.rename(real)
    said = stub_checkout.path / "temp.txt"
    python.write_text(f'#!/bin/sh\necho "$TMPDIR" > "{said}"\nexec "{real}" "$@"\n')
    python.chmod(0o755)

    # the environment the checker gives the probe, so coverage does not measure the stub
    probe(stub_checkout.path, side_environment(os.environ))

    assert Path(said.read_text().strip()).parent == system
    assert left_in(system) == []


def test_a_run_interrupted_with_ctrl_c_removes_its_folder(
    stub_checkout: StubCheckout, tmp_path: Path
) -> None:
    """give-legacy-runs-their-own-temp-folder-removes-its-folder"""
    system = tmp_path / "system"
    system.mkdir()
    stub_checkout.script({ONE_CHECK: {"sleep": 60}})
    argv = (sys.executable, "-m", "tools.compare_coverage", "--legacy", str(stub_checkout.path))
    argv += ("--target", ONE_CHECK, "--budget", "2")

    with subprocess.Popen(
        argv, cwd=REPO_ROOT, env=checker_environment(system), stdout=PIPE, stderr=PIPE, text=True
    ) as checker:
        try:
            folder = wait_for_call(stub_checkout, system)
            assert folder.is_dir()
            checker.send_signal(signal.SIGINT)
            _, stderr = checker.communicate(timeout=20)
        finally:
            checker.kill()

    assert checker.returncode == 130, stderr
    assert not folder.exists()
    assert left_in(system) == []


def wait_for_call(stub_checkout: StubCheckout, system: Path) -> Path:
    """The temp folder of the stub's call, once the stub has recorded it."""
    calls = stub_checkout.path / "calls.jsonl"
    deadline = time.monotonic() + INTERRUPT_WAIT
    while not (calls.exists() and calls.read_text().endswith("\n")):
        assert time.monotonic() < deadline, "the stub engine was never called"
        time.sleep(0.1)
    return ran_in(stub_checkout, system)

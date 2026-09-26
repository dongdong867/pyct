"""The legacy side through the adapter, against the stub engine, and the startup probe."""

import os
import platform
import sys
from pathlib import Path

import pytest

from tests.compare_coverage.conftest import REPO_ROOT, StubCheckout
from tools.compare_coverage.legacy_side import LegacyCheckoutError, LegacySide, probe
from tools.compare_coverage.process import side_environment
from tools.compare_coverage.sides import Limits, SideReport, SideRequest

ONE_CHECK = "targets.flip.one_check::classify"
ONE_CHECK_FILE = str(REPO_ROOT / "targets" / "flip" / "one_check.py")
ENVIRONMENT = side_environment(os.environ)


def request(target: str = ONE_CHECK, wait: float = 60) -> SideRequest:
    limits = Limits(budget=5.0, plateau=3, solver_timeout=2.5)
    return SideRequest(target=target, seed={"x": 0}, root=REPO_ROOT, limits=limits, wait=wait)


def test_the_side_reports_what_legacys_engine_answered(stub_checkout: StubCheckout) -> None:
    stub_checkout.script({ONE_CHECK: {"lines": [2, 4], "stopped": "timeout", "inputs": 7}})
    side = LegacySide(checkout=stub_checkout.path, environment=ENVIRONMENT)

    report = side.run(request())

    assert report == SideReport(
        file=ONE_CHECK_FILE, covered=frozenset({2, 4}), stopped="timeout", inputs=7
    )


def test_the_solver_timeout_is_rounded_up_to_whole_seconds(stub_checkout: StubCheckout) -> None:
    side = LegacySide(checkout=stub_checkout.path, environment=ENVIRONMENT)

    assert side.given(Limits(5.0, 3, 2.5)) == {"budget": 5.0, "plateau": 3, "solver_timeout": 3}


def test_an_engine_error_fails_the_side_with_legacys_text(stub_checkout: StubCheckout) -> None:
    stub_checkout.script({ONE_CHECK: {"success": False, "stopped": "error", "error": "boom"}})
    side = LegacySide(checkout=stub_checkout.path, environment=ENVIRONMENT)

    assert side.run(request()).failure == "error: boom"


def test_a_target_that_does_not_import_fails_the_side(stub_checkout: StubCheckout) -> None:
    side = LegacySide(checkout=stub_checkout.path, environment=ENVIRONMENT)

    report = side.run(request("targets.nowhere::f"))

    assert report.failure is not None
    assert report.failure.startswith("cannot import targets.nowhere::f: ModuleNotFoundError")


def test_a_silent_exit_is_no_summary_line(stub_checkout: StubCheckout) -> None:
    stub_checkout.script({ONE_CHECK: {"exit": 0}})
    side = LegacySide(checkout=stub_checkout.path, environment=ENVIRONMENT)

    assert side.run(request()).failure == "no summary line"


def test_a_side_past_its_wait_is_stopped(stub_checkout: StubCheckout) -> None:
    stub_checkout.script({ONE_CHECK: {"sleep": 30}})
    side = LegacySide(checkout=stub_checkout.path, environment=ENVIRONMENT)

    assert side.run(request(wait=1)).failure == "stopped after 1 s"


def test_the_probe_gives_legacys_python(stub_checkout: StubCheckout) -> None:
    assert probe(stub_checkout.path, ENVIRONMENT) == platform.python_version()


def test_the_probe_refuses_no_checkout() -> None:
    with pytest.raises(LegacyCheckoutError, match="--legacy is required.*\n.*git worktree add"):
        probe(None, ENVIRONMENT)


def test_the_probe_refuses_a_folder_with_no_environment(tmp_path: Path) -> None:
    with pytest.raises(
        LegacyCheckoutError, match=rf"no environment at {tmp_path}/.venv/bin/python"
    ):
        probe(tmp_path, ENVIRONMENT)


def test_the_probe_refuses_an_environment_without_legacys_engine(tmp_path: Path) -> None:
    python = tmp_path / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text(f'#!/bin/sh\nPYTHONPATH="{tmp_path}" exec "{sys.executable}" "$@"\n')
    python.chmod(0o755)
    # a pyct that fails to import stands for an environment where legacy is not installed
    (tmp_path / "pyct.py").write_text("raise ImportError('not here')\n")

    with pytest.raises(
        LegacyCheckoutError, match="engine cannot be imported: ImportError: not here"
    ):
        probe(tmp_path, ENVIRONMENT)


def test_the_probe_refuses_a_v2_checkout() -> None:
    with pytest.raises(
        LegacyCheckoutError, match="no run_concolic, so it is not a checkout of main"
    ):
        probe(REPO_ROOT, ENVIRONMENT)

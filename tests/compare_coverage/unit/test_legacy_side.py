"""The legacy side through the adapter, against the stub engine, and the startup probe."""

import os
import platform
import shutil
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from tests.compare_coverage.conftest import REPO_ROOT, StubCheckout
from tools.compare_coverage import legacy_side
from tools.compare_coverage.cache import Cache
from tools.compare_coverage.legacy_side import (
    LegacyCheckoutError,
    LegacySide,
    installed_distributions,
    probe,
)
from tools.compare_coverage.process import side_environment
from tools.compare_coverage.sides import Installed, Limits, SideReport, SideRequest

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


def test_the_side_says_which_version_of_the_requested_library_legacy_has(
    stub_checkout: StubCheckout, tmp_path: Path
) -> None:
    folder = stub_checkout.install(
        "fakelib", "1.0", {"fakelib/__init__.py": "def f(x):\n    return x\n"}
    )
    side = LegacySide(checkout=stub_checkout.path, environment=ENVIRONMENT)
    limits = Limits(budget=5.0)

    report = side.run(SideRequest("fakelib::f", {"x": 0}, tmp_path, limits, 60, "fakelib"))

    assert report.library == Installed(version="1.0", root=str(folder), provides=True)
    assert report.file == str(folder / "fakelib" / "__init__.py")
    assert side.run(request()).library is None


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


def test_a_non_zero_exit_names_the_code_and_what_it_said_last(
    stub_checkout: StubCheckout,
) -> None:
    stub_checkout.script({ONE_CHECK: {"exit": 3, "say": "boom"}})
    side = LegacySide(checkout=stub_checkout.path, environment=ENVIRONMENT)

    assert side.run(request()).failure == "exit 3: boom"


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


def test_the_probe_refuses_an_interpreter_that_cannot_start(tmp_path: Path) -> None:
    python = tmp_path / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("not a program")

    with pytest.raises(LegacyCheckoutError, match=rf"cannot start {python}: Permission denied"):
        probe(tmp_path, ENVIRONMENT)


def test_the_probe_says_when_the_import_does_not_answer(tmp_path: Path) -> None:
    python = tmp_path / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/sh\nexec sleep 60\n")
    python.chmod(0o755)

    with pytest.raises(LegacyCheckoutError, match="importing legacy's engine did not end in 1 s"):
        probe(tmp_path, ENVIRONMENT, wait=1)


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


def test_the_probe_refuses_an_engine_from_another_checkout(
    stub_checkout: StubCheckout, tmp_path: Path
) -> None:
    # an environment copied from elsewhere keeps importing that other checkout's engine
    other = tmp_path / "copied"
    python = other / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    shutil.copy(stub_checkout.path / ".venv" / "bin" / "python", python)
    engine = stub_checkout.path / "src" / "pyct" / "__init__.py"

    with pytest.raises(
        LegacyCheckoutError, match=rf"imports legacy's engine from {engine}, not {other}/src/pyct"
    ):
        probe(other, ENVIRONMENT)


def test_the_probe_refuses_a_v2_checkout() -> None:
    with pytest.raises(
        LegacyCheckoutError, match="no run_concolic, so it is not a checkout of main"
    ):
        probe(REPO_ROOT, ENVIRONMENT)


def cached_side(stub_checkout: StubCheckout, tmp_path: Path, refresh: bool = False) -> LegacySide:
    cache = Cache(folder=tmp_path / "cache", context="c", refresh_budget_spent=refresh)
    return LegacySide(checkout=stub_checkout.path, environment=ENVIRONMENT, cache=cache)


def test_a_kept_answer_is_reused_without_running_legacy(
    stub_checkout: StubCheckout, tmp_path: Path
) -> None:
    stub_checkout.script({ONE_CHECK: {"lines": [2, 4], "stopped": "timeout", "inputs": 7}})
    side = cached_side(stub_checkout, tmp_path)

    first = side.run(request())
    second = side.run(request())

    assert len(stub_checkout.calls()) == 1
    assert (first.reused, second.reused) == (False, True)
    assert replace(second, reused=False) == first


def test_a_budget_spent_answer_reruns_when_refreshing(
    stub_checkout: StubCheckout, tmp_path: Path
) -> None:
    stub_checkout.script({ONE_CHECK: {"lines": [2], "stopped": "timeout"}})
    cached_side(stub_checkout, tmp_path).run(request())

    report = cached_side(stub_checkout, tmp_path, refresh=True).run(request())

    assert len(stub_checkout.calls()) == 2
    assert not report.reused


@pytest.mark.parametrize(
    "script",
    [
        {"exit": 3, "say": "boom"},
        {"sleep": 5},
        {"success": False, "stopped": "error", "error": "boom"},
    ],
    ids=["exited", "stopped", "legacy failed"],
)
def test_a_side_that_did_not_answer_is_not_kept(
    stub_checkout: StubCheckout, tmp_path: Path, script: dict[str, object]
) -> None:
    stub_checkout.script({ONE_CHECK: script})
    side = cached_side(stub_checkout, tmp_path)

    side.run(request(wait=2))
    report = side.run(request(wait=2))

    assert len(stub_checkout.calls()) == 2
    assert report.failure is not None and not report.reused


def test_a_side_legacy_failed_on_its_own_timeout_is_kept_and_refreshed_when_asked(
    stub_checkout: StubCheckout, tmp_path: Path
) -> None:
    failed = {"success": False, "stopped": "timeout", "error": "child closed pipe"}
    stub_checkout.script({ONE_CHECK: failed})
    cached_side(stub_checkout, tmp_path).run(request())

    reused = cached_side(stub_checkout, tmp_path).run(request())
    refreshed = cached_side(stub_checkout, tmp_path, refresh=True).run(request())

    assert len(stub_checkout.calls()) == 2
    assert reused.reused and reused.failure == "timeout: child closed pipe"
    assert not refreshed.reused


def test_a_side_whose_library_probe_failed_is_not_kept(
    stub_checkout: StubCheckout, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unprobed(report: SideReport, *_args: object) -> SideReport:
        return replace(report, failure="cannot read which fakelib it has: no library line")

    monkeypatch.setattr(legacy_side, "with_library", unprobed)
    side = cached_side(stub_checkout, tmp_path)
    installed = SideRequest(ONE_CHECK, {"x": 0}, REPO_ROOT, Limits(budget=5.0), 60, "fakelib")

    side.run(installed)
    report = side.run(installed)

    assert len(stub_checkout.calls()) == 2
    assert not report.reused


def test_the_installed_distributions_are_the_names_in_the_environments_site_packages(
    tmp_path: Path,
) -> None:
    site = tmp_path / ".venv" / "lib" / "python3.12" / "site-packages"
    (site / "b-2.0.dist-info").mkdir(parents=True)
    (site / "a-1.0.dist-info").mkdir()
    (site / "a").mkdir()

    assert installed_distributions(tmp_path) == ("a-1.0.dist-info", "b-2.0.dist-info")
    assert installed_distributions(tmp_path / "none") == ()

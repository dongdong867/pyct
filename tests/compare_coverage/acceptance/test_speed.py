"""Acceptance tests for speed-up-the-compare-run: legacy results kept, rows run at once.

Each test runs the checker against the stub engine, which records every call, so a test
counts how often legacy ran. A stub checkout is kept only once a test commits it, as the
checker keeps the results of a git checkout only.
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from subprocess import PIPE

from tests.compare_coverage.acceptance.checker import (
    REPO_ROOT,
    a_run,
    checker_environment,
    compare_on,
    roots,
    rows,
    run_checker,
    summary,
    v2_side,
)
from tests.compare_coverage.conftest import StubCheckout
from tools.compare_coverage.cache import Cache
from tools.compare_coverage.compare import Sides
from tools.compare_coverage.entries import Entry
from tools.compare_coverage.legacy_side import LegacySide
from tools.compare_coverage.process import side_environment

# in the order targets.json lists them, the order rows print in
FOUR = (
    "targets.flip.nested_checks::bucket",
    "targets.flip.no_check::echo",
    "targets.flip.one_check::classify",
    "targets.flip.two_args::pick",
)

# how long each of FOUR's legacy sides sleeps when a test needs rows that take a while
SLEEP = 4


def targets(*names: str) -> list[str]:
    return [flag for name in names for flag in ("--target", name)]


def test_a_second_run_with_no_change_runs_no_legacy_side(stub_checkout: StubCheckout) -> None:
    """speed-up-the-compare-run-reuses-legacy"""
    stub_checkout.commit()
    argv = ("--legacy", str(stub_checkout.path), *targets(*FOUR[:2]), "--budget", "5")

    first = run_checker(*argv)
    second = run_checker(*argv)

    assert len(stub_checkout.calls()) == 2
    assert summary(first.stdout)["legacy_reused"] == 0
    assert summary(second.stdout, second.stderr)["legacy_reused"] == 2
    assert [row["legacy"]["reused"] for row in rows(second.stdout)] == [True, True]
    assert "legacy reused 2" in second.stderr.splitlines()[-1]
    assert statuses(first.stdout) == statuses(second.stdout)


def test_changing_one_target_file_reruns_only_that_rows_legacy_side(
    stub_checkout: StubCheckout, tmp_path: Path
) -> None:
    """speed-up-the-compare-run-reuses-legacy"""
    stub_checkout.commit()
    v2 = tmp_path / "v2"
    (v2 / "mine").mkdir(parents=True)
    for name in ("one", "two"):
        (v2 / "mine" / f"{name}.py").write_text("def f(x):\n    if x > 0:\n        return 1\n")
    entries = [Entry("v2", f"mine.{name}", "f", {"x": 0}) for name in ("one", "two")]
    cache = Cache(folder=tmp_path / "cache", context="c")
    legacy = LegacySide(stub_checkout.path, side_environment(os.environ), cache)
    sides = Sides(v2=v2_side(), legacy=legacy)
    run = a_run(entries, roots(stub_checkout.path, v2=v2))

    compare_on(run, sides)
    compare_on(run, sides)
    (v2 / "mine" / "two.py").write_text("def f(x):\n    if x > 1:\n        return 1\n")
    _, last, _ = compare_on(run, sides)

    one, two = str(v2 / "mine" / "one.py"), str(v2 / "mine" / "two.py")
    assert [call["config"]["scope"] for call in stub_checkout.calls()] == [[one], [two], [two]]
    assert [row["legacy"]["reused"] for row in last] == [True, False]


def test_rows_run_at_once_print_in_list_order_with_the_serial_answers(
    stub_checkout: StubCheckout,
) -> None:
    """speed-up-the-compare-run-runs-rows-at-once, speed-up-the-compare-run-keeps-the-answers"""
    # the first row takes longest, so it ends last when the rows run at once
    sleeps = dict(zip(FOUR, (SLEEP, 0, 0, 0), strict=True))
    stub_checkout.script({target: {"sleep": sleep} for target, sleep in sleeps.items()})
    argv = ("--legacy", str(stub_checkout.path), *targets(*FOUR), "--budget", "5")

    serial = run_checker(*argv, "--jobs", "1")
    together = run_checker(*argv, "--jobs", "4")

    assert [row["target"] for row in rows(together.stdout, together.stderr)] == list(FOUR)
    assert statuses(together.stdout) == statuses(serial.stdout)
    assert summary(together.stdout)["statuses"] == summary(serial.stdout)["statuses"]
    assert together.stderr.splitlines()[-1] == serial.stderr.splitlines()[-1]
    assert together.returncode == serial.returncode


def test_rows_run_at_once_take_less_than_their_sum(stub_checkout: StubCheckout) -> None:
    """speed-up-the-compare-run-runs-rows-at-once"""
    stub_checkout.script({target: {"sleep": SLEEP} for target in FOUR})
    argv = ("--legacy", str(stub_checkout.path), *targets(*FOUR), "--budget", "5")

    started = time.monotonic()
    result = run_checker(*argv, "--jobs", "4")
    took = time.monotonic() - started

    assert len(rows(result.stdout, result.stderr)) == len(FOUR)
    # one at a time, the legacy sides alone would sleep this long
    assert took < SLEEP * len(FOUR), took


def test_ctrl_c_stops_every_row_running_at_once(
    stub_checkout: StubCheckout, tmp_path: Path
) -> None:
    """speed-up-the-compare-run-runs-rows-at-once"""
    system = tmp_path / "system"
    system.mkdir()
    stub_checkout.script({target: {"sleep": 60} for target in FOUR[:2]})
    argv = (sys.executable, "-m", "tools.compare_coverage", "--legacy", str(stub_checkout.path))
    argv += (*targets(*FOUR[:2]), "--budget", "2", "--jobs", "2")

    with subprocess.Popen(
        argv, cwd=REPO_ROOT, env=checker_environment(system), stdout=PIPE, stderr=PIPE, text=True
    ) as checker:
        try:
            calls = wait_for_calls(stub_checkout, 2)
            checker.send_signal(signal.SIGINT)
            _, stderr = checker.communicate(timeout=20)
        finally:
            checker.kill()

    assert checker.returncode == 130, stderr
    assert list(system.iterdir()) == []
    assert all(gone(call["pid"]) for call in calls)


def wait_for_calls(stub_checkout: StubCheckout, count: int) -> list[dict[str, object]]:
    """The stub's calls, once it has recorded ``count`` whole lines."""
    calls = stub_checkout.path / "calls.jsonl"
    deadline = time.monotonic() + 30
    while not calls.exists() or calls.read_text().count("\n") < count:
        assert time.monotonic() < deadline, "the stub engine was not called for every row"
        time.sleep(0.1)
    return stub_checkout.calls()


def gone(pid: object) -> bool:
    """True once ``pid`` no longer runs."""
    assert isinstance(pid, int)
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.1)
    return False


def statuses(stdout: str) -> list[tuple[str, str]]:
    return [(row["target"], row["status"]) for row in rows(stdout)]

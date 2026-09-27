import contextlib
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from pyct.sweep.listing import PackageImportError, list_package
from pyct.sweep.rows import Row, Status
from tests.acceptance.harness import REPO_ROOT

ROUGH = "targets.sweep.rough"
STALL = "targets.sweep.stall"
UNREAD = "targets.sweep.unread"

# a lister stand-in answers --after with nothing left to list
DONE_AFTER = (
    'import sys\nif "--after" in sys.argv:\n    print(\'{"done": true}\')\n    sys.exit()\n'
)


def stand_in(script: str) -> tuple[str, ...]:
    """A lister that runs ``script``, handed the package and any ``--after`` as arguments."""
    return (sys.executable, "-c", script)


@pytest.fixture(autouse=True)
def from_the_repository_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(REPO_ROOT)


def failed(module: str, ended: str) -> Row:
    return Row(module, None, Status.FAILED, reason=f"cannot import {module}: {ended}")


def test_every_module_gets_its_row_whatever_its_import_did() -> None:
    assert list_package(ROUGH) == (
        failed(f"{ROUGH}.broken", "ValueError('boom')"),
        failed(f"{ROUGH}.crashes", "killed by SIGSEGV"),
        failed(f"{ROUGH}.exits", "exited with code 3"),
        failed(f"{ROUGH}.gone", "ValueError('boom')"),
        Row(f"{ROUGH}.prices", "total", Status.LISTED, seed={"n": 0}),
        failed(f"{ROUGH}.quits", "SystemExit(0)"),
        Row(f"{ROUGH}.zeta", "last", Status.LISTED, seed={"n": 0}),
    )


def test_a_name_that_raises_when_read_costs_its_module_a_row_and_nothing_more() -> None:
    raised = "RuntimeError('settings are not configured')"

    def unread(module: str) -> Row:
        return Row(module, None, Status.FAILED, reason=f"cannot read {module}::settings: {raised}")

    assert list_package(UNREAD) == (
        unread(UNREAD),
        Row(UNREAD, "home", Status.LISTED, seed={"n": 0}),
        unread(f"{UNREAD}.conf"),
        Row(
            f"{UNREAD}.lazy",
            None,
            Status.FAILED,
            reason=f"cannot read {UNREAD}.lazy: RuntimeError("
            "'__all__ is made on first use, and making it failed')",
        ),
        Row(f"{UNREAD}.swapped.inner", "deep", Status.LISTED, seed={"n": 0}),
        unread(f"{UNREAD}.views"),
        Row(f"{UNREAD}.views", "page", Status.LISTED, seed={"n": 0}),
        Row(f"{UNREAD}.views.detail", "detail", Status.LISTED, seed={"n": 0}),
    )


def test_a_package_that_forwards_to_itself_is_walked_below() -> None:
    forwarded = "targets.sweep.forwarded"
    assert list_package(forwarded) == (
        Row(f"{forwarded}.sub", "below", Status.LISTED, seed={"n": 0}),
    )


def test_an_import_with_no_fact_within_the_grace_is_stopped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pids = tmp_path / "pids"
    monkeypatch.setenv("SWEEP_PIDS_FILE", str(pids))

    rows = list_package(STALL, grace=2)

    assert rows == (
        failed(f"{STALL}.hangs", "did not finish in 2 s"),
        Row(f"{STALL}.zeta", "last", Status.LISTED, seed={"n": 0}),
    )
    for pid in pids.read_text().split():
        with pytest.raises(ProcessLookupError):
            os.kill(int(pid), 0)


@pytest.mark.parametrize(
    ("package", "grace", "message"),
    [
        pytest.param("targets.sweep.fails", 60, "ValueError('boom')", id="raises"),
        pytest.param(f"{ROUGH}.crashes", 60, "killed by SIGSEGV", id="crashes"),
        pytest.param(f"{STALL}.hangs", 1, "did not finish in 1 s", id="hangs"),
    ],
)
def test_a_package_that_does_not_import_stops_the_listing(
    package: str, grace: float, message: str
) -> None:
    with pytest.raises(PackageImportError) as raised:
        list_package(package, grace=grace)

    assert str(raised.value) == f"cannot import {package}: {message}"


def test_an_entry_several_modules_give_is_one_row_and_rows_come_in_order() -> None:
    script = DONE_AFTER + (
        "for module in ('p', 'p.b', 'p.a'):\n"
        '    print(\'{"importing": "%s"}\' % module)\n'
        '    print(\'{"entry": {"module": "p.a", "name": "f", "seed": null, '
        '"skip": "no parameter to vary"}}\')\n'
        'print(\'{"entry": {"module": "p.b", "name": "g", "seed": {"n": 0}, '
        '"skip": null}}\')\n'
        "print('{\"done\": true}')\n"
    )

    assert list_package("p", lister=stand_in(script)) == (
        Row("p.a", "f", Status.SKIPPED, reason="no parameter to vary"),
        Row("p.b", "g", Status.LISTED, seed={"n": 0}),
    )


def test_a_bound_method_two_modules_export_is_one_row_under_the_module_of_its_code() -> None:
    dice = "targets.sweep.dice"
    assert list_package(dice) == (Row(f"{dice}.core", "roll", Status.LISTED, seed={"sides": 0}),)


def test_a_line_the_lister_ends_part_way_is_no_line() -> None:
    script = DONE_AFTER + (
        'sys.stdout.write(\'{"importing": "p.m"}\\n{"entry": \')\nsys.stdout.flush()\nsys.exit(4)\n'
    )

    assert list_package("p", lister=stand_in(script)) == (failed("p.m", "exited with code 4"),)


def test_a_process_left_holding_the_pipe_does_not_keep_sweep_waiting(tmp_path: Path) -> None:
    pid_file = tmp_path / "pid"
    script = DONE_AFTER + (
        "import subprocess\n"
        'print(\'{"importing": "p.m"}\', flush=True)\n'
        "left = subprocess.Popen(['/bin/sleep', '30'])\n"
        f"open({str(pid_file)!r}, 'w').write(str(left.pid))\n"
    )
    started = time.monotonic()

    rows = list_package("p", grace=20, lister=stand_in(script))

    assert rows == (failed("p.m", "exited with code 0"),)
    assert time.monotonic() - started < 10
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_file.read_text()), 0)


def test_a_lister_that_closes_its_output_and_runs_on_is_stopped() -> None:
    script = "import os, time\nos.close(1)\ntime.sleep(30)\n"

    with pytest.raises(PackageImportError) as raised:
        list_package("p", grace=0.5, lister=stand_in(script))

    assert str(raised.value) == "cannot import p: did not finish in 0.5 s"


def test_a_lister_that_ends_before_its_first_fact_fails_the_package() -> None:
    with pytest.raises(PackageImportError) as raised:
        list_package("p", lister=stand_in("import sys\nsys.exit(1)\n"))

    assert str(raised.value) == "cannot import p: exited with code 1"


def test_a_sigterm_ends_the_listing_as_a_ctrl_c_does_and_stops_the_lister(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pids = tmp_path / "pids"
    monkeypatch.setenv("SWEEP_PIDS_FILE", str(pids))

    def terminate_once_the_import_hangs() -> None:
        while not (pids.exists() and pids.read_text().endswith("\n")):
            time.sleep(0.05)
        os.kill(os.getpid(), signal.SIGTERM)

    threading.Thread(target=terminate_once_the_import_hangs, daemon=True).start()
    before = signal.getsignal(signal.SIGTERM)

    with pytest.raises(KeyboardInterrupt):
        list_package(STALL, grace=30)

    assert signal.getsignal(signal.SIGTERM) == before
    for pid in pids.read_text().split():
        with pytest.raises(ProcessLookupError):
            os.kill(int(pid), 0)


# starts a command with SIGHUP at its default, whatever the test runner got, as under nohup
WITH_SIGHUP = (
    "import os, signal, sys\n"
    "signal.signal(signal.SIGHUP, signal.SIG_{action})\n"
    "os.execv(sys.executable, [sys.executable, *sys.argv[1:]])\n"
)


def killed(pids: Path) -> None:
    """SIGKILL every process the pid file names that is still there, so a failure leaks none."""
    for pid in pids.read_text().split() if pids.exists() else []:
        with contextlib.suppress(ProcessLookupError):
            os.kill(int(pid), signal.SIGKILL)


def test_a_sighup_stops_the_lister_and_ends_the_sweep_by_it(tmp_path: Path) -> None:
    # a closing terminal sends SIGHUP; the lister leads its own session and never gets it
    pids = tmp_path / "pids"
    env = {name: value for name, value in os.environ.items() if name != "PYTHONPATH"}
    env["SWEEP_PIDS_FILE"] = str(pids)
    sweep = subprocess.Popen(
        [sys.executable, "-c", WITH_SIGHUP.format(action="DFL"), "-P", "-m", "pyct"]
        + ["sweep", STALL, "--list"],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        while not (pids.exists() and pids.read_text().endswith("\n")):
            time.sleep(0.05)
        alive = pids.read_text().split()
        sweep.send_signal(signal.SIGHUP)
        ended = sweep.wait(timeout=20)
    finally:
        sweep.kill()
        killed(pids)

    # a shell reports it as exit 129
    assert ended == -signal.SIGHUP
    for pid in alive:
        with pytest.raises(ProcessLookupError):
            os.kill(int(pid), 0)


def test_an_ignored_sighup_stays_ignored() -> None:
    # under nohup the terminal's SIGHUP is ignored, and sweep must not start heeding it; a
    # process of its own, so a sweep that did heed it ends that process and not the tests
    lister = DONE_AFTER + (
        "import os, signal\nos.kill(os.getppid(), signal.SIGHUP)\nprint('{\"done\": true}')\n"
    )
    check = (
        "import signal, sys\n"
        "from pyct.sweep.listing import list_package\n"
        f"rows = list_package('p', lister=(sys.executable, '-c', {lister!r}))\n"
        "print(rows == (), signal.getsignal(signal.SIGHUP) is signal.SIG_IGN)\n"
    )
    finished = subprocess.run(
        [sys.executable, "-c", WITH_SIGHUP.format(action="IGN"), "-c", check],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert (finished.returncode, finished.stdout) == (0, "True True\n"), finished.stderr

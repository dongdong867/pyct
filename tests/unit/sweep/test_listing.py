import os
import sys
import time
from pathlib import Path

import pytest

from pyct.sweep.listing import PackageImportError, list_package
from pyct.sweep.rows import Row, Status
from tests.acceptance.harness import REPO_ROOT

ROUGH = "targets.sweep.rough"
STALL = "targets.sweep.stall"

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

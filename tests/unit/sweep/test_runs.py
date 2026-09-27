import os
from pathlib import Path

import pytest

from pyct.sweep.result import SweepLimits
from pyct.sweep.rows import Row, Status
from pyct.sweep.runs import run_entry
from tests.unit.sweep.stand_ins import PYCT

LIMITS = SweepLimits(budget=30.0, plateau=5, solver_timeout=10.0, grace=0.5)


def entry(name: str) -> Row:
    return Row("p", name, Status.LISTED, seed={"n": 0})


def ran(name: str, budget: float = 2.5) -> Row:
    return run_entry(entry(name), LIMITS, budget=budget, pyct=PYCT)


def test_a_run_that_prints_its_summary_and_exits_zero_ran_with_it() -> None:
    row = ran("ran")

    assert (row.status, row.seed, row.reason) == (Status.RAN, {"n": 0}, None)
    assert row.run is not None
    assert row.run["argv"] == [
        "run",
        "p::ran",
        "--args",
        '{"n": 0}',
        "--budget",
        "2.5",
        "--plateau",
        "5",
        "--solver-timeout",
        "10.0",
    ]


def test_each_run_starts_in_a_fresh_empty_directory_deleted_after_it() -> None:
    first, second = ran("ran").run, ran("ran").run
    assert first is not None and second is not None

    assert first["files"] == [] and second["files"] == []
    assert first["cwd"] != second["cwd"]
    assert not Path(str(first["cwd"])).exists()


def test_the_run_is_handed_the_working_directory_to_import_from(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    run = ran("ran").run
    assert run is not None

    assert run["imports_from"] == os.getcwd()


def test_a_run_that_exits_badly_fails_with_its_last_line_and_keeps_its_summary() -> None:
    row = ran("exits")

    assert (row.status, row.reason) == (Status.FAILED, "exit 1: solver failed")
    assert row.run is not None and row.run["stopped"] == "no fork to flip"


def test_a_run_with_no_summary_line_fails_though_it_exits_zero() -> None:
    row = ran("silent")

    assert (row.status, row.reason, row.run) == (Status.FAILED, "exit 0: ", None)


def test_a_run_a_signal_ends_fails_by_the_signal_and_a_line_it_cut_short_is_no_summary() -> None:
    row = ran("crashes")

    assert (row.status, row.reason, row.run) == (Status.FAILED, "killed by SIGSEGV", None)


def test_a_run_still_going_past_its_budget_and_the_grace_is_stopped() -> None:
    row = ran("hangs", budget=0.1)

    assert (row.status, row.reason, row.run) == (
        Status.FAILED,
        "stopped 0.5 s past its budget",
        None,
    )


@pytest.mark.parametrize(("name", "code"), [("stray", 1), ("stray_then_zero", 0)])
def test_a_line_the_target_prints_with_stopped_is_no_summary(name: str, code: int) -> None:
    row = ran(name)

    assert (row.status, row.run) == (Status.FAILED, None)
    assert row.reason == f"exit {code}: "

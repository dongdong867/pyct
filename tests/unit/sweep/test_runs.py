import json
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


# a line with the shape of pyct run's summary line
SUMMARY: dict[str, object] = {
    "stopped": "no fork to flip",
    "inputs": 2,
    "solver": {"sat": 1, "unsat": 0, "unknown": 0, "timeout": 0},
    "misses": [],
    "covered": {"m.py": [1, 2]},
    "total": {"m.py": 4},
    "uncovered": {"m.py": [3]},
    "environment": {"python": "3.12.14", "cvc5": "1.3.4", "platform": "p", "isolated": True},
}

# every key in turn, with a value of the wrong type
WRONG = [
    ("stopped", 1),
    ("inputs", "2"),
    ("inputs", True),
    ("solver", [1]),
    ("solver", {"sat": "1"}),
    ("misses", "none"),
    ("covered", 1),
    ("covered", [1, 2]),
    ("covered", {"m.py": ["1"]}),
    ("covered", {"m.py": [True]}),
    ("total", "4"),
    ("total", {"m.py": 4.0}),
    ("uncovered", {"m.py": 3}),
    ("environment", None),
]


def printed(line: dict[str, object], monkeypatch: pytest.MonkeyPatch) -> Row:
    monkeypatch.setenv("SWEEP_TEST_LINE", json.dumps(line))
    return ran("prints")


def test_a_line_with_the_summarys_shape_is_the_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    row = printed(SUMMARY, monkeypatch)

    assert (row.status, row.run) == (Status.RAN, SUMMARY)


@pytest.mark.parametrize(("key", "value"), WRONG)
def test_a_line_with_every_key_but_one_of_the_wrong_type_is_no_summary(
    key: str, value: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = printed({**SUMMARY, key: value}, monkeypatch)

    assert (row.status, row.reason, row.run) == (Status.FAILED, "exit 0: ", None)

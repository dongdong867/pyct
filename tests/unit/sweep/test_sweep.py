import json
from pathlib import Path
from typing import cast

import pytest

from pyct.solver.locate import SolverMissingError
from pyct.sweep import sweep as sweeping
from pyct.sweep.listing import PackageImportError
from pyct.sweep.result import SweepLimits, SweepStop
from pyct.sweep.rows import Row, Status
from pyct.sweep.sweep import SPENT, Mode, Programs, SweepTell, sweep
from tests.unit.sweep.stand_ins import PYCT, lister

LIMITS = SweepLimits(grace=0.5)


def entry(module: str, name: str, skip: str | None = None) -> str:
    seed = None if skip else {"n": 0}
    return json.dumps({"entry": {"module": module, "name": name, "seed": seed, "skip": skip}})


# two entries to run, with one skipped and a module that did not import between them
PROGRAMS = Programs(
    lister=lister(
        json.dumps({"importing": "p"}),
        entry("p.a", "f"),
        entry("p.a", "g", skip="no parameter to vary"),
        json.dumps({"failed": "p.a.gone", "reason": "ValueError('boom')"}),
        entry("p.b", "h"),
    ),
    pyct=PYCT,
)


@pytest.fixture(autouse=True)
def a_cvc5(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """A cvc5 that is always found, at version 9.9; the list of calls says whether it was."""
    looked: list[str] = []
    monkeypatch.setattr(sweeping, "locate", lambda: looked.append("locate") or Path("cvc5"))
    monkeypatch.setattr(sweeping, "version", lambda path: "9.9")
    return looked


def told() -> tuple[SweepTell, list[object]]:
    said: list[object] = []
    tell = SweepTell(
        starting=lambda row, number, count: said.append((row.name, number, count)),
        row=lambda row: said.append(row.name or row.module),
    )
    return tell, said


def test_each_listed_entry_runs_in_order_and_each_row_is_told_as_it_is_known() -> None:
    tell, said = told()
    result = sweep("p", limits=LIMITS, tell=tell, programs=PROGRAMS)

    assert said == [("f", 1, 2), "f", "g", "p.a.gone", ("h", 2, 2), "h"]
    assert [(row.name, row.status) for row in result.rows] == [
        ("f", Status.RAN),
        ("g", Status.SKIPPED),
        (None, Status.FAILED),
        ("h", Status.RAN),
    ]
    assert (result.stopped, result.cvc5) == (SweepStop.DONE, "9.9")


def test_the_runs_sum_their_lines_by_file() -> None:
    result = sweep("p", limits=LIMITS, programs=PROGRAMS)

    assert result.covered == {"m.py": frozenset({1, 2, 3})}
    assert result.total == {"m.py": 4}


def test_each_run_gets_the_limits_given() -> None:
    limits = SweepLimits(budget=7.0, plateau=3, solver_timeout=2.0, grace=0.5)
    result = sweep("p", limits=limits, programs=PROGRAMS)

    run = result.rows[0].run
    assert run is not None
    assert cast("list[str]", run["argv"])[4:] == [
        "--budget",
        "7.0",
        "--plateau",
        "3",
        "--solver-timeout",
        "2.0",
    ]
    assert result.limits == limits


def test_an_entry_runs_with_no_more_than_the_total_budget_has_left() -> None:
    limits = SweepLimits(budget=100.0, total_budget=30.0, grace=0.5)
    result = sweep("p", limits=limits, programs=PROGRAMS)

    run = result.rows[0].run
    assert run is not None
    assert 0 < float(cast("list[str]", run["argv"])[5]) < 30
    assert result.stopped is SweepStop.DONE


def test_an_entry_the_total_budget_leaves_no_time_is_skipped_with_its_seed() -> None:
    tell, said = told()
    limits = SweepLimits(total_budget=1e-9, grace=0.5)
    result = sweep("p", limits=limits, tell=tell, programs=PROGRAMS)

    spent = Row("p.a", "f", Status.SKIPPED, seed={"n": 0}, reason=SPENT)
    assert result.rows[0] == spent
    assert result.rows[3].reason == SPENT
    assert not any(isinstance(item, tuple) for item in said)
    assert result.stopped is SweepStop.TOTAL_BUDGET_SPENT


def test_a_listing_runs_nothing_and_looks_for_no_cvc5(a_cvc5: list[str]) -> None:
    tell, said = told()
    result = sweep("p", limits=LIMITS, mode=Mode.LIST, tell=tell, programs=PROGRAMS)

    assert [row.status for row in result.rows] == [
        Status.LISTED,
        Status.SKIPPED,
        Status.FAILED,
        Status.LISTED,
    ]
    assert said == ["f", "g", "p.a.gone", "h"]
    assert (result.stopped, result.cvc5, a_cvc5) == (SweepStop.LISTED, None, [])


def test_a_run_without_cvc5_stops_before_any_row(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.undo()
    monkeypatch.setenv("PATH", str(tmp_path))
    tell, said = told()

    with pytest.raises(SolverMissingError):
        sweep("p", limits=LIMITS, tell=tell, programs=PROGRAMS)
    assert said == []


def test_a_package_that_does_not_import_stops_the_sweep() -> None:
    programs = Programs(
        lister=lister(json.dumps({"failed": "p", "reason": "ValueError('boom')"})), pyct=PYCT
    )

    with pytest.raises(PackageImportError):
        sweep("p", limits=LIMITS, programs=programs)


def test_an_entry_whose_target_prints_a_line_like_a_summary_costs_only_its_row() -> None:
    programs = Programs(lister=lister(entry("p.a", "stray"), entry("p.b", "h")), pyct=PYCT)
    result = sweep("p", limits=LIMITS, programs=programs)

    assert [(row.status, row.run is None) for row in result.rows] == [
        (Status.FAILED, True),
        (Status.RAN, False),
    ]
    assert result.covered == {"m.py": frozenset({2, 3})}


def test_every_entry_keeps_its_substituted_code_in_one_cache_where_the_sweep_runs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PYCT_CACHE_DIR", raising=False)
    result = sweep("p", limits=LIMITS, programs=PROGRAMS)

    caches = {row.run["cache"] for row in result.rows if row.run is not None}
    assert caches == {str(tmp_path / ".pyct_cache")}


def test_a_cache_folder_already_named_is_kept_and_named_from_where_the_sweep_runs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PYCT_CACHE_DIR", "kept")
    result = sweep("p", limits=LIMITS, programs=PROGRAMS)

    caches = {row.run["cache"] for row in result.rows if row.run is not None}
    assert caches == {str(tmp_path / "kept")}

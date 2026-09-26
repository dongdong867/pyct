"""Acceptance tests for compare-coverage-on-the-fixtures: files with no entry, entries left out.

Both go through ``compare()`` with sides that answer from a script, because what they check
is the list, not either engine.
"""

from collections.abc import Mapping
from pathlib import Path

import pytest

from tests.compare_coverage.acceptance.checker import a_run, compare_on
from tools.compare_coverage.compare import Sides
from tools.compare_coverage.entries import (
    LIST_FILE,
    Entry,
    Origin,
    load_list,
    parse_list,
    unlisted_files,
)
from tools.compare_coverage.sides import Limits, SideReport, SideRequest


class ScriptedSide:
    """A side that reports the given lines in the file the request's root and target name."""

    def __init__(self, lines: frozenset[int]) -> None:
        self.lines = lines

    def given(self, limits: Limits) -> Mapping[str, float]:
        return {"budget": limits.budget}

    def run(self, request: SideRequest) -> SideReport:
        module = request.target.split("::")[0]
        file = request.root.joinpath(*module.split(".")).with_suffix(".py")
        return SideReport(file=str(file), covered=self.lines, stopped="done", inputs=1)


class UncalledSide:
    def given(self, limits: Limits) -> Mapping[str, float]:
        return {}

    def run(self, request: SideRequest) -> SideReport:
        pytest.fail(f"a side ran {request.target}")


def checkouts(tmp_path: Path) -> dict[Origin, Path]:
    """A v2 checkout with a listed target and a new one, a legacy one with an old fixture."""
    v2, legacy = tmp_path / "v2", tmp_path / "legacy"
    fixtures = legacy / "tests" / "acceptance" / "fixtures"
    (v2 / "targets").mkdir(parents=True)
    fixtures.mkdir(parents=True)
    for file in (v2 / "targets" / "listed.py", v2 / "targets" / "new.py", fixtures / "old.py"):
        file.write_text("def f(x: int) -> int:\n    return x\n")
    return {Origin.V2: v2, Origin.LEGACY: legacy}


def test_reports_an_unlisted_file(tmp_path: Path) -> None:
    """compare-coverage-against-legacy-reports-an-unlisted-file"""
    roots = checkouts(tmp_path)
    v2, fixtures = roots[Origin.V2], roots[Origin.LEGACY] / "tests" / "acceptance" / "fixtures"
    target_list = parse_list(
        {
            "sets": {
                "v2": {"origin": "v2", "scan": "targets"},
                "fixtures": {"origin": "legacy", "scan": "tests/acceptance/fixtures"},
            },
            "entries": [{"set": "v2", "target": "targets.listed::f", "seed": {"x": 0}}],
        }
    )
    unlisted = unlisted_files(target_list, ["v2", "fixtures"], roots)
    run = a_run(target_list.entries, roots, unlisted=unlisted)
    same = ScriptedSide(frozenset({2}))

    code, (listed, new, old), stderr = compare_on(run, Sides(v2=same, legacy=same))

    assert listed["status"] == "same"
    assert (new["status"], new["set"], new["file"]) == (
        "not listed",
        "v2",
        str(v2 / "targets" / "new.py"),
    )
    assert (old["status"], old["set"], old["file"]) == (
        "not listed",
        "fixtures",
        str(fixtures / "old.py"),
    )
    assert str(v2 / "targets" / "new.py") in stderr
    assert code == 1


def test_shows_a_left_out_entry(tmp_path: Path) -> None:
    """compare-coverage-against-legacy-shows-a-left-out-entry"""
    committed = load_list(LIST_FILE).select(["v2"], [])
    (broken,) = [entry for entry in committed if entry.module == "targets.trace.broken_import"]
    assert broken == Entry(
        set="v2", module="targets.trace.broken_import", left_out="fails to import by design"
    )
    run = a_run([broken], {Origin.V2: Path(LIST_FILE).parents[2], Origin.LEGACY: tmp_path})

    code, (row,), stderr = compare_on(run, Sides(v2=UncalledSide(), legacy=UncalledSide()))

    assert row["status"] == "left out"
    assert row["left_out"] == "fails to import by design"
    assert "fails to import by design" in stderr
    assert code == 0

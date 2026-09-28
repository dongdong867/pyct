"""pyct's process holds the cyclic collector off while it handles each finished input."""

import dataclasses
import gc

import pytest

from pyct.branches.tree import Tree
from pyct.results.coverage import Coverage
from pyct.results.record import InputRecord
from pyct.run.isolation import Isolation
from pyct.run.run import Tell, run
from pyct.run.target import load_target


@pytest.mark.parametrize("isolation", [Isolation.AUTO, Isolation.IN_PROCESS])
def test_each_report_and_its_path_are_handled_with_the_collector_off(
    isolation: Isolation, monkeypatch: pytest.MonkeyPatch
) -> None:
    reported: list[bool] = []
    added: list[bool] = []
    add = Tree.add

    def adding(tree: Tree, forks: tuple[object, ...]) -> None:
        added.append(gc.isenabled())
        add(tree, forks)  # pyrefly: ignore[bad-argument-type]

    def report(record: InputRecord, coverage: Coverage) -> None:
        reported.append(gc.isenabled())

    monkeypatch.setattr(Tree, "add", adding)
    target = load_target("targets.trace.uncalled_helper::classify")

    run(target, {"x": 1}, isolation=isolation, tell=Tell(report=report))

    assert reported == added == [False, False]
    assert gc.isenabled()


def test_the_target_runs_with_the_collector_as_the_run_found_it() -> None:
    target = load_target("targets.trace.uncalled_helper::classify")
    seen: list[bool] = []
    original = target.fn

    def watched(x: int) -> object:
        seen.append(gc.isenabled())
        return original(x)

    run(dataclasses.replace(target, fn=watched), {"x": 1}, isolation=Isolation.IN_PROCESS)

    assert seen == [True, True]

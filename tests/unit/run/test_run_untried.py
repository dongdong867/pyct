"""run() counts the forks it left untried at each site, for why_uncovered's not_tried count."""

from pathlib import Path

import pytest

from pyct.binding.bind import Seed
from pyct.branches.tree import Tree
from pyct.config.budget import Budget
from pyct.config.limits import Limits
from pyct.config.plateau import Plateau
from pyct.core.branch import ForkSite, Site
from pyct.results.record import StopKind
from pyct.run.isolation import Isolation
from pyct.run.process import InputStartError
from pyct.run.run import Bounds, _attempt, run
from pyct.run.target import load_target
from pyct.solver.answer import Error

REPO_ROOT = Path(__file__).resolve().parents[3]
TWO_OTHER_SIDES = str(REPO_ROOT / "targets" / "flip" / "two_other_sides_empty.py")
ONE_CHECK = str(REPO_ROOT / "targets" / "flip" / "one_check.py")
SPINS = str(REPO_ROOT / "targets" / "flip" / "spins_after_a_check.py")


def test_a_run_that_emptied_the_tree_left_nothing_untried() -> None:
    target = load_target("targets.flip.one_check::classify")

    result = run(target, {"x": 3}, isolation=Isolation.IN_PROCESS)

    assert result.stopped.kind is StopKind.NO_FORK
    assert result.untried == {}


def test_a_plateau_stop_counts_the_fork_it_picked_and_never_solved() -> None:
    target = load_target("targets.flip.two_other_sides_empty::mark")

    result = run(
        target,
        {"x": 3, "y": 3},
        limits=Limits(plateau=Plateau(inputs=1)),
        isolation=Isolation.IN_PROCESS,
    )

    assert result.stopped.kind is StopKind.NO_GAIN
    # `y < 10` was flipped; the pick of `x < 10` came before the plateau stop, and it ran nothing
    assert result.untried == {ForkSite(Site(file=TWO_OTHER_SIDES, line=3, col=7)): 1}


def test_a_solver_failure_counts_the_fork_being_solved(monkeypatch: pytest.MonkeyPatch) -> None:
    target = load_target("targets.flip.one_check::classify")
    monkeypatch.setattr("pyct.run.run.solve", lambda *args: Error("cvc5: boom"))

    result = run(target, {"x": 3}, isolation=Isolation.IN_PROCESS)

    assert result.stopped.kind is StopKind.SOLVER_FAILED
    assert result.untried == {ForkSite(Site(file=ONE_CHECK, line=2, col=7)): 1}


def test_an_input_that_cannot_start_leaves_its_fork_untried() -> None:
    target = load_target("targets.flip.one_check::classify")
    seed = {"x": 3}
    tree = Tree()
    tree.add(run(target, seed, isolation=Isolation.IN_PROCESS).records[0].forks)

    def refused(args: object, until: float | None) -> object:
        raise InputStartError("could not start a child process")

    attempt = _attempt(refused, {0: Seed.of(seed)}, tree, Bounds(), ())  # pyrefly: ignore[bad-argument-type]

    assert attempt.stop is not None
    assert attempt.unrun == ForkSite(Site(file=ONE_CHECK, line=2, col=7))


def test_a_budget_stop_counts_every_fork_still_open() -> None:
    target = load_target("targets.flip.spins_after_a_check::spin")

    # in pyct's process, so the fork comes before the deadline however slow a process starts
    limits = Limits(budget=Budget(seconds=0.2))
    result = run(target, {"x": 3}, limits=limits, isolation=Isolation.IN_PROCESS)

    # the seed forked on `x < 10`, then spun past the deadline, so that fork was never tried
    assert result.stopped.kind is StopKind.BUDGET
    assert result.untried == {ForkSite(Site(file=SPINS, line=2, col=7)): 1}

"""Acceptance tests for the count-time-as-well-as-inputs-when-stuck story through ``run()``: a run
with an LLM tool whose solver asks run to their limit is stuck once a quarter of its budget
passes with no new line, before 5 inputs pass.

The target's four conditions each read ``float`` of an argument, which the solver runs out of
its 1 s on, so the seed's path leaves four forks that each take at least 1 s and give no input.
Each run has rewrites on with a fake provider that answers nothing; no test calls a model.
"""

from dataclasses import dataclass

import pytest

from pyct.config.budget import Budget
from pyct.config.limits import Limits
from pyct.config.solver_timeout import SolverTimeout
from pyct.results.llm_asks import AskCost, Unanswered, Why
from pyct.run import stuck
from pyct.run.loop import Loop
from pyct.run.stuck import STRETCH_SHARE
from tests.acceptance.llm_rewrites import FakeRewrites, one_thread, run_rewrites  # noqa: F401

EXPONENTS = "targets.rewrites.exponents::exponents"
SEED = {"s": "0", "t": "0", "u": "0", "v": "0"}
REFUSED = Unanswered(Why.PROVIDER, "provider error 500", AskCost(1))
BUDGET = 6.0


@dataclass(frozen=True)
class Held:
    """One moment as it was held: the run's inputs and the forks still open as it started, and
    when it started and ended on the budget's clock, as seconds of the budget used."""

    inputs: int
    open_forks: int
    started: float
    ended: float


@pytest.fixture
def moments(monkeypatch: pytest.MonkeyPatch) -> list[Held]:
    """Each moment the run held, noted as ``Stuck.hold`` is called."""
    held: list[Held] = []
    hold = stuck.Stuck.hold

    def noted(self: stuck.Stuck, run: stuck.Running) -> None:
        assert isinstance(run, Loop)
        inputs, open_forks = len(run.records), sum(run.tree.untried().values())
        started = _used(run)
        hold(self, run)
        held.append(Held(inputs, open_forks, started, _used(run)))

    monkeypatch.setattr(stuck.Stuck, "hold", noted)
    return held


def _used(run: Loop) -> float:
    """The seconds of the budget the run used so far, 0 with no budget: its waits for the model
    are not counted, since each moved the deadline later."""
    until = run.bounds.until
    return 0.0 if until is None else BUDGET - (until - stuck.time.monotonic())


def limits(budget: float | None) -> Limits:
    return Limits(budget=Budget(budget), solver_timeout=SolverTimeout(1.0))


# count-time-as-well-as-inputs-when-stuck-after-a-quarter-of-the-budget
def test_a_quarter_of_the_budget_with_no_new_line_brings_a_moment_while_forks_are_open(
    moments: list[Held],
) -> None:
    provider = FakeRewrites([REFUSED])

    run_rewrites(EXPONENTS, SEED, provider, limits(BUDGET))

    first = moments[0]
    # before 5 inputs, and with a fork of the seed's path still to try
    assert first.inputs < 5
    assert first.open_forks > 0
    assert first.started >= BUDGET * STRETCH_SHARE
    assert provider.requests


# count-time-as-well-as-inputs-when-stuck-not-with-no-budget
def test_a_run_with_no_budget_is_stuck_only_once_no_fork_is_left(moments: list[Held]) -> None:
    run_rewrites(EXPONENTS, SEED, FakeRewrites([REFUSED]), limits(None))

    assert [held.open_forks for held in moments][:1] == [0]


# count-time-as-well-as-inputs-when-stuck-counts-from-the-moment-s-end
@pytest.mark.serial
def test_the_next_stretch_counts_from_the_moment_s_end_and_not_the_model_s_wait(
    moments: list[Held],
) -> None:
    # each ask waits 2 s, more than the stretch, which the budget's clock does not count
    provider = FakeRewrites([REFUSED], delay=2.0)

    run_rewrites(EXPONENTS, SEED, provider, limits(BUDGET))

    first, second = moments[:2]
    assert second.started - first.ended >= BUDGET * STRETCH_SHARE

"""Acceptance tests for the take-a-formula-out-of-use-when-its-fork-times-out story.

Each run goes through ``run()`` with summaries on and a fake provider, as
``tests/acceptance/lost_calls.py`` has it. The run's solver asks go to a fake that notes each
limit and whether the plan's prefix holds a fork that reads a formula, and answers as cvc5
does, unless a test answers itself. No test calls a model.
"""

import pytest

from pyct.binding.bind import Seed
from pyct.branches.plan import Plan
from pyct.config.limits import Limits
from pyct.config.plateau import Plateau
from pyct.config.solver_timeout import SolverTimeout
from pyct.core.foundation.branch import Branch, Fact
from pyct.run import loop as loop_module
from pyct.run.loop import Solved
from tests.acceptance.llm_summaries import (
    FakeSummaries,
    one_thread,  # noqa: F401
    run_summaries,
)
from tests.acceptance.lost_calls import FORKED, MOD

# a run that goes on well past its first turn, with a solver timeout of 4 s
LIMITS = Limits(plateau=Plateau(20), solver_timeout=SolverTimeout(4))

# each ask's limit, with whether its plan's prefix holds a fork that reads a formula
type Asks = list[tuple[float, bool]]


def noting(monkeypatch: pytest.MonkeyPatch) -> Asks:
    """The list that gets each solver ask of the run, in run order, as the fake takes it."""
    asks: Asks = []
    real = loop_module.solver_answer

    def solved(
        wanted: Plan, origin: Seed, limit: float, asked: tuple[Branch | Fact, ...] | None = None
    ) -> Solved:
        asks.append((limit, any(fork.formulas for fork in wanted.prefix)))
        return real(wanted, origin, limit, asked)

    monkeypatch.setattr(loop_module, "solver_answer", solved)
    return asks


# llm-summary-a-formula-s-path-gets-a-quarter-of-the-solver-limit
def test_an_ask_whose_path_holds_a_formula_s_fork_gets_a_quarter_of_the_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asks = noting(monkeypatch)

    run_summaries(FORKED, {"n": 2}, FakeSummaries([MOD]), LIMITS)

    marked = [limit for limit, holds in asks if holds]
    plain = [limit for limit, holds in asks if not holds]
    assert marked, asks
    assert plain, asks
    assert set(marked) == {1.0}, asks
    assert set(plain) == {4.0}, asks

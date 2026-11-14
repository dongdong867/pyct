"""Acceptance tests for the a-slow-unknown-waits-as-a-timeout-does ticket.

Each runs ``run()`` on ``targets/rewrites/loops.py`` from the seed ``{"s": "0", "n": 0}``, every
input in this process. The run's ask about ``float(s) == 1e-30`` on line 5 goes to a fake that
answers ``unknown`` and says the ask took a share of the limit it was given, so whether the
answer is slow does not rest on how busy the machine is. Every other ask goes to the real cvc5.
"""

import pytest

from pyct.binding.bind import Seed
from pyct.branches.plan import Plan
from pyct.config.limits import Limits
from pyct.config.plateau import Plateau
from pyct.core.foundation.branch import Branch, Fact
from pyct.results.record import RunResult
from pyct.run import loop as loop_module
from pyct.run.isolation import Isolation
from pyct.run.loop import Solved
from pyct.run.run import run
from pyct.run.setup import Setup
from pyct.run.target import interception, load_target
from pyct.run.tell import Ask, Tell
from pyct.solver.answer import Unknown
from tests.acceptance.llm_rewrites import one_thread  # noqa: F401

LOOPS = "targets.rewrites.loops::loops"
SEED = {"s": "0", "n": 0}
# `while count < n:`
LOOP = 3
# `if float(s) == 1e-30:`, whose compare the fake answers; its `isfloat(s)` fork, which comes
# before a raise, goes to cvc5
HARD = 5
# a plain run stops once 6 inputs in a row cover no new line
PLAIN = Limits(plateau=Plateau(6))


def answering_unknown(monkeypatch: pytest.MonkeyPatch, share: float) -> None:
    """The run's ask about line 5's compare answers ``unknown`` at once, and says it took
    ``share`` of its limit."""
    real = loop_module.solver_answer

    def solved(
        wanted: Plan, origin: Seed, limit: float, asked: tuple[Branch | Fact, ...] | None = None
    ) -> Solved:
        if wanted.aim.site.line != HARD or wanted.aim.raising:
            return real(wanted, origin, limit, asked)
        return Solved(Unknown(), limit * share, Ask(0, wanted.aim, wanted.path, ()))

    monkeypatch.setattr(loop_module, "solver_answer", solved)


def plain_run(limits: Limits) -> tuple[list[tuple[int, bool]], RunResult]:
    """A run with no LLM tool: each ask's aimed line and whether its fork comes before a raise,
    in run order, and the result."""
    aims: list[tuple[int, bool]] = []
    tell = Tell(asked=lambda ask: aims.append((ask.aim.site.line, ask.aim.raising)))
    setup = Setup(isolation=Isolation.IN_PROCESS)
    with interception(LOOPS):
        result = run(load_target(LOOPS), SEED, limits=limits, setup=setup, tell=tell)
    return aims, result


# a-slow-unknown-waits-for-the-last-picks-a-quick-unknown-keeps-its-place
def test_a_quick_unknown_leaves_its_site_first_on_the_next_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answering_unknown(monkeypatch, 0.24)

    aims, _ = plain_run(PLAIN)

    # the seed's path: the compare, then its `isfloat`, then the loop; the loop's input's path
    # reaches line 5 and its compare is asked about next, before the loop's deeper fork
    assert aims[:4] == [(HARD, False), (HARD, True), (LOOP, False), (HARD, False)], aims

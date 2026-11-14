"""Acceptance tests for the a-slow-unknown-waits-as-a-timeout-does ticket.

Each runs ``run()`` on ``targets/rewrites/loops.py`` from the seed ``{"s": "0", "n": 0}``, every
input in this process. The run's ask about ``float(s) == 1e-30`` on line 5 goes to a fake that
answers ``unknown`` and says how long the ask took, a share of the limit it was given, so whether
the answer is slow does not rest on how busy the machine is. A run with rewrites measures each
ask's seconds itself, so there the fake waits that long. Every other ask goes to the real cvc5.
"""

import time
from collections.abc import Callable

import pytest

from pyct.binding.bind import Seed
from pyct.branches.plan import Plan
from pyct.config.budget import Budget
from pyct.config.limits import Limits
from pyct.config.plateau import Plateau
from pyct.config.solver_timeout import SolverTimeout
from pyct.core.foundation.branch import Branch, Fact
from pyct.results.causes import Reason
from pyct.results.record import MissWhy, RunResult, Source
from pyct.run import loop as loop_module
from pyct.run.isolation import Isolation
from pyct.run.loop import Solved
from pyct.run.run import run
from pyct.run.setup import Setup
from pyct.run.target import interception, load_target
from pyct.run.tell import Ask, Tell
from pyct.solver.answer import Answer, Timeout, Unknown
from tests.acceptance.llm_rewrites import (
    FakeRewrites,
    file_of,
    one_thread,  # noqa: F401
    run_rewrites,
)

LOOPS = "targets.rewrites.loops::loops"
F = file_of("loops")
SEED = {"s": "0", "n": 0}
# `while count < n:`
LOOP = 3
# `if float(s) == 1e-30:`, whose compare the fake answers; its `isfloat(s)` fork, which comes
# before a raise, goes to cvc5
HARD = 5
# `return 1`, under line 5's true side
UNDER = 6
# a plain run stops once 6 inputs in a row cover no new line
PLAIN = Limits(plateau=Plateau(6))

# what the fake answers for an ask given a limit: the answer, and the seconds it says it took
type Gives = Callable[[float], tuple[Answer, float]]


def answering(monkeypatch: pytest.MonkeyPatch, gives: Gives) -> None:
    """The run's ask about line 5's compare answers what ``gives`` says."""
    real = loop_module.solver_answer

    def solved(
        wanted: Plan, origin: Seed, limit: float, asked: tuple[Branch | Fact, ...] | None = None
    ) -> Solved:
        if wanted.aim.site.line != HARD or wanted.aim.raising:
            return real(wanted, origin, limit, asked)
        answer, seconds = gives(limit)
        return Solved(answer, seconds, Ask(0, wanted.aim, wanted.path, ()))

    monkeypatch.setattr(loop_module, "solver_answer", solved)


def answering_unknown(monkeypatch: pytest.MonkeyPatch, share: float) -> None:
    """The run's ask about line 5's compare answers ``unknown`` at once, and says it took
    ``share`` of its limit."""
    answering(monkeypatch, lambda limit: (Unknown(), limit * share))


def answering_after(monkeypatch: pytest.MonkeyPatch, seconds: float) -> None:
    """The run's ask about line 5's compare waits ``seconds`` and answers ``unknown``; when its
    limit is less, it waits out the limit and answers ``timeout``, as cvc5 does."""

    def gives(limit: float) -> tuple[Answer, float]:
        started = time.monotonic()
        time.sleep(min(seconds, limit))
        answer = Unknown() if seconds < limit else Timeout()
        return answer, time.monotonic() - started

    answering(monkeypatch, gives)


def plain_run(limits: Limits) -> tuple[list[tuple[int, bool]], RunResult]:
    """A run with no LLM tool: each ask's aimed line and whether its fork comes before a raise,
    in run order, and the result."""
    aims: list[tuple[int, bool]] = []
    tell = Tell(asked=lambda ask: aims.append((ask.aim.site.line, ask.aim.raising)))
    setup = Setup(isolation=Isolation.IN_PROCESS)
    with interception(LOOPS):
        result = run(load_target(LOOPS), SEED, limits=limits, setup=setup, tell=tell)
    return aims, result


# a-slow-unknown-waits-for-the-last-picks-on-later-paths
def test_a_slow_unknown_sends_the_next_asks_to_the_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answering_unknown(monkeypatch, 0.78)

    aims, result = plain_run(PLAIN)

    # line 5's site, its `isfloat` fork too, waits behind the loop's forks, of which each new
    # path has one more
    assert aims[0] == (HARD, False), aims
    assert [line for line, _ in aims[1:]] == [LOOP] * (len(aims) - 1), aims
    assert result.stopped.plateau == PLAIN.plateau.inputs, result.stopped


# a-slow-unknown-waits-for-the-last-picks-at-a-quarter-of-the-limit
def test_an_unknown_at_exactly_a_quarter_of_its_limit_waits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answering_unknown(monkeypatch, 0.25)

    aims, _ = plain_run(PLAIN)

    assert aims[:3] == [(HARD, False), (LOOP, False), (LOOP, False)], aims


# a-slow-unknown-waits-for-the-last-picks-a-quick-unknown-keeps-its-place
def test_a_quick_unknown_leaves_its_site_first_on_the_next_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answering_unknown(monkeypatch, 0.24)

    aims, _ = plain_run(PLAIN)

    # the seed's path: the compare, then its `isfloat`, then the loop; the loop's input's path
    # reaches line 5 and its compare is asked about next, before the loop's deeper fork
    assert aims[:4] == [(HARD, False), (HARD, True), (LOOP, False), (HARD, False)], aims


# a-slow-unknown-waits-for-the-last-picks-reaches-a-stuck-moment
@pytest.mark.parametrize("seconds", [1.8, 2.0], ids=["unknown", "timeout"])
def test_a_run_with_rewrites_reaches_a_stuck_moment_within_its_budget(
    monkeypatch: pytest.MonkeyPatch, seconds: float
) -> None:
    # the check's case at a fifth of its scale: 1.8 s of a 2 s limit, in a 6 s budget. Asking
    # line 5 first on each path, 4 asks spend the budget, one input short of a stuck moment
    answering_after(monkeypatch, seconds)
    provider = FakeRewrites(['s == "1e-30"'])
    limits = Limits(budget=Budget(6), solver_timeout=SolverTimeout(2.0))

    ran = run_rewrites(LOOPS, SEED, provider, limits)

    assert [request.place for request in provider.requests] == [
        f"targets.rewrites.loops:{HARD}:7"
    ], ran.said
    [found] = [record for record in ran.records if record.source is Source.REWRITE]
    assert found.args == {"s": "1e-30", "n": found.args["n"]}
    assert UNDER in found.covered_lines


# a-slow-unknown-waits-for-the-last-picks-still-says-unknown
def test_a_slow_unknown_still_says_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    # 0.3 s of a 1 s limit is slow, and leaves each real cvc5 ask the rest of a second; a rewrite
    # whose input never takes the side leaves line 6
    answering_after(monkeypatch, 0.3)
    provider = FakeRewrites(['s == "2"'])
    limits = Limits(plateau=Plateau(12), solver_timeout=SolverTimeout(1.0))

    ran = run_rewrites(LOOPS, SEED, provider, limits)

    result = ran.result
    assert {miss.why for miss in result.misses if miss.site.line == HARD} == {MissWhy.UNKNOWN}
    assert (result.solver.unknown > 0, result.solver.timeout) == (True, 0), result.solver
    [why] = [entry for entry in result.why_uncovered if UNDER in entry.lines]
    assert why.reason is Reason.NOT_TAKEN and why.tries is not None, why
    assert (why.tries.unknown > 0, why.tries.timeout) == (True, 0), why.tries
    request = provider.requests[0]
    assert (request.place, request.answer) == (f"targets.rewrites.loops:{HARD}:7", "unknown")

"""Acceptance tests for the ask-for-a-stuck-loop-s-summary story through ``run()``, across a run's
moments: a later moment asks again about a loop with no checked formula and leaves a checked one
alone, and no moment comes once no tool can still ask.

Each run has summaries on with a fake provider; no test calls a model.
"""

import pytest

from pyct.config.limits import Limits
from pyct.config.plateau import Plateau
from pyct.results.llm_asks import AskCost, Unanswered, Why
from pyct.results.record import RunResult
from pyct.run import loop, stuck
from pyct.run.isolation import Isolation
from pyct.run.run import run
from pyct.run.setup import Setup
from pyct.run.target import interception, load_target
from tests.acceptance.llm_summaries import (
    COUNT,
    COUNTS,
    SEED,
    TOKENS,
    F,
    FakeSummaries,
    Summarized,
    code_reply,
    one_thread,  # noqa: F401
    run_summaries,
)

AT = f"llm: summary for the loop at {F}:10"
PLACE = "targets.why.stuck:10:4"
# a plateau that ends the run 3 inputs after its second moment, so it holds two
TWO_MOMENTS = Limits(plateau=Plateau(13))
LENGTH = 'def summary(s, t):\n    return {"t": len(s)}'


@pytest.fixture
def moments(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """The inputs the run had at each moment it held, counted as ``Stuck.hold`` is called."""
    held: list[int] = []
    hold = stuck.Stuck.hold

    def counted(self: stuck.Stuck, run: stuck.Running) -> None:
        held.append(len(run.records))
        hold(self, run)

    monkeypatch.setattr(stuck.Stuck, "hold", counted)
    return held


@pytest.fixture
def causes(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """The inputs the run had each time it worked out the causes of its missed lines, counted as
    ``Loop.causes``, the run's one call of the cause analysis, is called."""
    worked_out: list[int] = []
    causes_of = loop.Loop.causes

    def counted(self: loop.Loop, stop_at: float | None) -> object:
        worked_out.append(len(self.records))
        return causes_of(self, stop_at)

    monkeypatch.setattr(loop.Loop, "causes", counted)
    return worked_out


def plain(limits: Limits) -> RunResult:
    """``counts`` from the seed with no LLM tool, its loops recorded as a summaries run records
    them."""
    setup = Setup(isolation=Isolation.IN_PROCESS)
    with interception(COUNTS, pieces=True):
        return run(load_target(COUNTS), SEED, limits=limits, setup=setup)


def summary_lines(done: Summarized) -> list[str]:
    return [line for line in done.llm_said() if line.startswith("llm: summary for")]


# llm-summary-for-a-stuck-loop-asked-again-at-the-next-moment
def test_a_loop_whose_formula_failed_is_asked_about_again_with_the_failed_formula() -> None:
    provider = FakeSummaries([code_reply(LENGTH), COUNT])

    done = run_summaries(COUNTS, SEED, provider, TWO_MOMENTS)

    first, second = provider.requests
    assert first.place == second.place == PLACE
    assert first.tries == ()
    [earlier] = second.tries
    assert LENGTH in earlier.formula
    assert earlier.reason == "at input 1, t was 0, the formula gave 2"
    assert provider.tries == {PLACE: 2}
    assert summary_lines(done) == [
        f"{AT}: t = len(s)",
        f"{AT}, try 1: at input 1, t was 0, the formula gave 2",
        f'{AT}: t = t + s.count("z")',
        f"{AT}: checked on {provider.inputs_then[1]} past runs",
    ]
    assert provider.inputs_then[0] < provider.inputs_then[1]
    [loop] = done.result.summaries
    assert (loop.tries, loop.checked_on) == (2, provider.inputs_then[1])


# llm-summary-for-a-stuck-loop-checked-is-not-asked-again
def test_a_loop_whose_formula_is_checked_is_not_asked_about_again(moments: list[int]) -> None:
    provider = FakeSummaries([COUNT])

    done = run_summaries(COUNTS, SEED, provider, TWO_MOMENTS)

    assert len(moments) >= 2
    assert len(provider.requests) == 1
    assert summary_lines(done) == [
        f'{AT}: t = t + s.count("z")',
        f"{AT}: checked on {provider.inputs_then[0]} past runs",
    ]


# llm-stuck-moment-needs-a-tool-that-can-ask-token-limit
def test_no_moment_comes_once_the_first_moment_s_ask_reached_the_token_limit(
    causes: list[int],
) -> None:
    provider = FakeSummaries([COUNT], limit=sum(TOKENS))

    done = run_summaries(COUNTS, SEED, provider, TWO_MOMENTS)

    # the first moment's causes, and none after it
    assert causes == provider.inputs_then
    assert len(provider.requests) == 1
    alone = plain(TWO_MOMENTS)
    assert done.result.stopped == alone.stopped
    assert [record.args for record in done.records] == [record.args for record in alone.records]


# llm-stuck-moment-needs-a-tool-that-can-ask-after-a-failed-ask
def test_a_second_moment_comes_after_an_ask_that_failed(moments: list[int]) -> None:
    failed = Unanswered(Why.PROVIDER, "provider error 500", AskCost(1))
    provider = FakeSummaries([failed, COUNT])

    done = run_summaries(COUNTS, SEED, provider, TWO_MOMENTS)

    assert len(moments) >= 2
    assert [request.place for request in provider.requests] == [PLACE, PLACE]
    assert provider.inputs_then == moments[:2]
    assert f"{AT}: checked on {provider.inputs_then[1]} past runs" in done.said

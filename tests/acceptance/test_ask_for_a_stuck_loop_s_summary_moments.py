"""Acceptance tests for the ask-for-a-stuck-loop-s-summary story through ``run()``, across a run's
moments: a later moment asks again about a loop with no checked formula and leaves a checked one
alone.

Each run has summaries on with a fake provider; no test calls a model.
"""

import pytest

from pyct.config.limits import Limits
from pyct.config.plateau import Plateau
from pyct.run import stuck
from tests.acceptance.llm_summaries import (
    COUNT,
    COUNTS,
    SEED,
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

"""Acceptance tests for the take-a-formula-out-of-use-when-its-fork-times-out story.

Each run goes through ``run()`` with summaries on and a fake provider, as
``tests/acceptance/lost_calls.py`` has it. The run's solver asks go to a fake that notes each
limit and whether the plan's prefix holds a fork that reads a formula, and answers as cvc5
does, unless a test answers itself. No test calls a model.
"""

import json
import re
from collections.abc import Callable

import pytest

from pyct.binding.bind import Seed
from pyct.branches.plan import Plan
from pyct.config.limits import Limits
from pyct.config.plateau import Plateau
from pyct.config.solver_timeout import SolverTimeout
from pyct.core.foundation.branch import Branch, Fact
from pyct.results.jsonl import render_summary
from pyct.results.llm_asks import LlmUse
from pyct.run import loop as loop_module
from pyct.run.loop import Solved
from pyct.run.tell import Ask
from pyct.solver.answer import Answer, Timeout, Unknown
from tests.acceptance.llm_summaries import (
    COUNT,
    SEED,
    TOKENS,
    FakeSummaries,
    G,
    Summarized,
    code_reply,
    one_thread,  # noqa: F401
    run_summaries,
)
from tests.acceptance.lost_calls import BOUNDED, DEEP, FORKED, MOD, at
from tests.acceptance.test_track_a_value_through_a_call_summary import downgraded
from tests.acceptance.test_track_a_value_through_a_loop_summary import LOOPS, line_of

# a run that goes on well past its first turn, with a solver timeout of 4 s
LIMITS = Limits(plateau=Plateau(20), solver_timeout=SolverTimeout(4))

# each ask's limit, with whether its plan's prefix holds a fork that reads a formula
type Asks = list[tuple[float, bool]]


# what the fake answers an ask whose path holds a fork that reads a formula's value, given its
# limit: the answer and the seconds it says it took, or None to leave the ask to cvc5
type Gives = Callable[[float], tuple[Answer, float] | None]


def noting(monkeypatch: pytest.MonkeyPatch, gives: Gives | None = None) -> Asks:
    """The list that gets each solver ask of the run, in run order, as the fake takes it."""
    asks: Asks = []
    real = loop_module.solver_answer

    def solved(
        wanted: Plan, origin: Seed, limit: float, asked: tuple[Branch | Fact, ...] | None = None
    ) -> Solved:
        marked = any(fork.formulas for fork in wanted.prefix)
        asks.append((limit, marked))
        given = gives(limit) if marked and gives is not None else None
        if given is None:
            return real(wanted, origin, limit, asked)
        return Solved(given[0], given[1], Ask(0, wanted.aim, wanted.path, ()))

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


def timing_out_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """The first ask whose path holds a fork that reads a formula's value times out after its
    whole limit; every later ask goes to cvc5."""
    timed_out: list[float] = []

    def gives(limit: float) -> tuple[Answer, float] | None:
        if timed_out:
            return None
        timed_out.append(limit)
        return Timeout(), limit

    noting(monkeypatch, gives)


def states_of(done: Summarized) -> list[tuple[int, object]]:
    """Each formula's line and state, from the summary line's ``llm.summaries``."""
    use = LlmUse("openai:gpt-6-luna", ("summaries",))
    items = json.loads(render_summary(done.result, use))["llm"]["summaries"]
    return [(item["line"], item["state"]) for item in items]


def taken_out(done: Summarized, at_site: str, what: str = "call __pow__") -> list[tuple[int, str]]:
    """Each ``taken out of use`` line about ``at_site``, as its input's number and its reason."""
    said = rf"llm: summary for the {what} at {re.escape(at_site)} taken out of use at input"
    found = [re.fullmatch(rf"{said} (\d+): (.*)", line) for line in done.llm_said()]
    return [(int(each[1]), each[2]) for each in found if each is not None]


# the site of `pow(n, 2, 10)` in `bounded`, and of its fork `r > 9`, as stderr writes them
POW = at(84, 8)
LATER_FORK = at(87, 7)


# llm-summary-taken-out-of-use-when-its-fork-runs-long
def test_a_call_formula_whose_fork_times_out_goes_out_of_use(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timing_out_once(monkeypatch)
    provider = FakeSummaries([MOD], limit=sum(TOKENS))

    done = run_summaries(BOUNDED, {"n": 2}, provider, LIMITS)

    [(_, reason)] = taken_out(done, POW)
    assert reason == f"its fork at {LATER_FORK} timed out"
    assert states_of(done) == [(84, "dropped")]
    line = next(each for each in done.llm_said() if "taken out of use" in each)
    said = done.said.index(line)
    later = done.records[sum(each.startswith("input ") for each in done.said[:said]) :]
    assert later
    for record in later:
        assert downgraded(record, "__pow__") == [POW], record


# llm-summary-taken-out-of-use-when-its-fork-runs-long, for an `unknown`
def test_a_slow_unknown_on_a_formula_s_path_takes_it_out_and_a_quick_one_does_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    noting(monkeypatch, lambda limit: (Unknown(), limit * 0.3))
    slow = run_summaries(BOUNDED, {"n": 2}, FakeSummaries([MOD], limit=sum(TOKENS)), LIMITS)

    [(_, reason)] = taken_out(slow, POW)
    assert re.fullmatch(
        rf"its fork at {re.escape(LATER_FORK)} answered unknown after 0.30 s", reason
    )
    assert states_of(slow) == [(84, "dropped")]

    noting(monkeypatch, lambda limit: (Unknown(), limit * 0.1))
    quick = run_summaries(BOUNDED, {"n": 2}, FakeSummaries([MOD], limit=sum(TOKENS)), LIMITS)

    assert taken_out(quick, POW) == []
    assert states_of(quick) == [(84, "in use")]


# llm-summary-taken-out-of-use-when-its-fork-runs-long, for a loop
def test_a_loop_formula_whose_fork_times_out_goes_out_of_use(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timing_out_once(monkeypatch)
    provider = FakeSummaries([COUNT], limit=sum(TOKENS))

    done = run_summaries(f"{LOOPS}::capped", SEED, provider, LIMITS)

    loop = line_of("capped", "for c in s:")
    fork = f"{G}:{line_of('capped', 'if t == 4:')}:7"
    [(_, reason)] = taken_out(done, f"{G}:{loop}", "loop")
    assert reason == f"its fork at {fork} timed out"
    assert states_of(done) == [(loop, "dropped")]
    assert not any(record.drops for record in done.records)


# the sites, in `deep`, of its four `pow` calls: the last one's answer is the one `k == 5` reads
BITS = [(36, 8), (37, 8), (38, 8), (40, 11)]
BITS_REPLIES = [
    code_reply(f'def summary(n):\n    return {{"answer": n % {2**by}}}') for by in (1, 2, 3, 4)
]


# llm-summary-taken-out-only-for-its-own-terms
def test_only_the_formula_whose_value_the_path_reads_goes_out_of_use(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timing_out_once(monkeypatch)
    provider = FakeSummaries(BITS_REPLIES, limit=4 * sum(TOKENS))

    done = run_summaries(DEEP, {"n": 3}, provider, LIMITS)

    assert [taken_out(done, at(*site)) != [] for site in BITS] == [False, False, False, True]
    assert states_of(done) == [(36, "in use"), (37, "in use"), (38, "in use"), (40, "dropped")]


# llm-summary-asked-again-after-it-is-taken-out
def test_a_formula_taken_out_is_asked_about_again_with_why(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timing_out_once(monkeypatch)
    provider = FakeSummaries([MOD, MOD])

    done = run_summaries(BOUNDED, {"n": 2}, provider, LIMITS)

    [(number, reason)] = taken_out(done, POW)
    assert len(provider.requests) == 2
    again = provider.requests[1]
    [earlier] = again.tries
    assert earlier.reason == f"taken out of use at input {number}: {reason}"
    assert states_of(done) == [(84, "in use")]

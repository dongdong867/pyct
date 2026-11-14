"""The token limit is one fact for the run: once any ask's answer leaves no token, the seeds
ask's included, no LLM tool asks again and no stuck moment comes, through ``run()`` with
summaries and rewrites both on."""

from collections.abc import Mapping

import pytest

from pyct.config.budget import Budget
from pyct.config.limits import Limits
from pyct.config.plateau import Plateau
from pyct.config.solver_timeout import SolverTimeout
from pyct.results.llm_asks import AskCost
from pyct.results.record import RunResult
from pyct.run import loop
from pyct.run.helpers import Helpers
from pyct.run.isolation import Isolation
from pyct.run.llm_seeds import SeedReply
from pyct.run.run import run
from pyct.run.setup import Setup
from pyct.run.target import interception, load_target
from pyct.run.token_limit import TokenLimit
from tests.acceptance.fake_seeds import FakeSeeds
from tests.acceptance.llm_rewrites import FakeRewrites
from tests.acceptance.llm_summaries import (
    COUNT,
    COUNTS,
    SEED,
    TOKENS,
    FakeSummaries,
    one_thread,  # noqa: F401
)

# limits under which a run would hold a moment every 5 inputs, up to the cap of 3 that ask
LONG = Limits(budget=Budget(60), plateau=Plateau(40), solver_timeout=SolverTimeout(1.0))
LOOPS = "targets.rewrites.loops::loops"


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


def ran(spec: str, seed: Mapping[str, object], helpers: Helpers) -> RunResult:
    """``run()`` on ``spec`` with ``helpers``, its package recording each loop's runs."""
    setup = Setup(isolation=Isolation.IN_PROCESS, helpers=helpers)
    with interception(spec, pieces=True):
        return run(load_target(spec), seed, limits=LONG, setup=setup)


def test_a_summaries_reply_that_reaches_the_limit_ends_every_tool_s_asks(
    causes: list[int],
) -> None:
    summaries = FakeSummaries([COUNT], limit=sum(TOKENS))
    rewrites = FakeRewrites(['s == "1e-30"'])

    ran(COUNTS, SEED, Helpers(summaries=summaries, rewrites=rewrites))

    assert len(summaries.requests) == 1
    assert len(causes) == 1
    assert rewrites.requests == []


def test_a_rewrites_reply_that_reaches_the_limit_ends_every_tool_s_asks(
    causes: list[int],
) -> None:
    # the first moment's fourth and last ask reaches the limit
    rewrites = FakeRewrites(['s == "1e-29"'], limit=4 * sum(TOKENS))
    summaries = FakeSummaries([COUNT])

    ran(LOOPS, {"s": "0", "n": 0}, Helpers(summaries=summaries, rewrites=rewrites))

    assert len(rewrites.requests) == 4
    assert len(causes) == 1


def test_a_seeds_reply_that_reaches_the_limit_leaves_no_moment(causes: list[int]) -> None:
    seeds = FakeSeeds(SeedReply(('{"s": "zz"}',), AskCost(1, *TOKENS, tokens_left=0)))
    summaries = FakeSummaries([COUNT])

    result = ran(COUNTS, SEED, Helpers(seeds=seeds, summaries=summaries))

    assert len(result.records) > 7
    assert causes == []
    assert summaries.requests == []


@pytest.mark.parametrize(("left", "reached"), [(5, False), (None, False), (0, True)])
def test_the_limit_is_reached_by_an_answer_that_left_no_token(
    left: int | None, reached: bool
) -> None:
    limit = TokenLimit()

    limit.heard(AskCost(1, tokens_left=left))

    assert limit.reached is reached

"""Acceptance tests for the summarize-a-missed-branch story's no-fork lines: rewrites ask about a
missed line whose condition records no fork and reads no value lost at a call, and summaries take
one whose value was lost at a call.

Each runs ``run()`` with a fake ``RewriteProvider``, and a fake ``SummaryProvider`` where summaries
are on; no test calls a model.
"""

from pyct.config.limits import Limits
from pyct.config.plateau import Plateau
from pyct.config.solver_timeout import SolverTimeout
from pyct.results.record import Source
from tests.acceptance.harness import REPO_ROOT
from tests.acceptance.llm_rewrites import FakeRewrites, llm_said, run_rewrites
from tests.acceptance.llm_summaries import (
    FakeSummaries,
    one_thread,  # noqa: F401
)
from tests.acceptance.lost_calls import SHIFTED, WRONG, C, place

# `counts(s)`: a loop counts the "z"s of `s` into `t`, and `if t > 25:` on line 13 guards
# `return "many"` on line 14
COUNTS = "targets.why.stuck::counts"
STUCK = str(REPO_ROOT / "targets" / "why" / "stuck.py")
MANY = 's == "zzzzzzzzzzzzzzzzzzzzzzzzzz"'
# a plateau that ends the run soon after its first moment
LIMITS = Limits(plateau=Plateau(10), solver_timeout=SolverTimeout(1.0))


# llm-rewrite-no-fork-loop-sources-go-to-rewrites
def test_a_no_fork_line_whose_sources_are_loops_covers_its_line() -> None:
    provider = FakeRewrites([MANY])

    ran = run_rewrites(COUNTS, {"s": "a"}, provider, LIMITS)

    [request] = provider.requests
    assert (request.condition.text, request.condition.side) == ("t > 25", True)
    assert request.place == "targets.why.stuck:13:7"
    assert request.answer == "no fork"
    assert request.args == (("s", '"a"'),)
    assert f"llm: rewrite for {STUCK}:13:7: took the wanted side" in llm_said(ran.said)
    [line_14] = [record for record in ran.records if 14 in record.covered_lines]
    assert line_14.source is Source.REWRITE


# llm-rewrite-no-fork-lost-values-go-to-summaries
def test_a_lost_value_s_no_fork_line_goes_to_summaries_and_rewrites_send_nothing() -> None:
    rewrites = FakeRewrites(["n == 2"])
    # a formula that fails its check, so line 17 stays missed
    summaries = FakeSummaries([WRONG])

    ran = run_rewrites(SHIFTED, {"n": 3}, rewrites, LIMITS, summaries)

    assert place(11, 11) in [request.place for request in summaries.requests]
    assert 17 in ran.result.coverage.uncovered[C]
    assert rewrites.requests == []

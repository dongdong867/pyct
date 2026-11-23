"""Acceptance tests for the label-the-inputs-a-summary-gave story through ``run()``: a moment that
puts a formula in use runs again the latest input the formula was checked on, labeled ``summary``,
and a solver input whose aimed fork reads a value a formula gave is labeled ``summary`` too.

Each run has summaries on with a fake provider, its package intercepted with the recording of
each loop's runs, and each input in a forked child unless it says otherwise; no test calls a
model.
"""

from pyct.config.limits import Limits
from pyct.config.plateau import Plateau
from pyct.results.record import InputRecord, Source, StopKind
from pyct.run.isolation import Isolation
from tests.acceptance.llm_summaries import (
    COUNT,
    SEED,
    FakeSummaries,
    Summarized,
    one_thread,  # noqa: F401
    run_summaries,
)
from tests.acceptance.test_track_a_value_through_a_loop_summary import (
    LOOPS,
    Z,
    after_checked,
    before_checked,
    forks_at,
    line_of,
)

ENCODED_Z = f"{LOOPS}::encoded_z"
# a run that goes on well past its first moment
LONGER = Limits(plateau=Plateau(20))


def encoded(isolation: Isolation = Isolation.AUTO) -> Summarized:
    """``encoded_z`` run from the seed, the provider answering ``COUNT``."""
    provider = FakeSummaries([COUNT])
    done = run_summaries(ENCODED_Z, SEED, provider, LONGER, isolation)
    assert len(provider.requests) == 1, done.said
    return done


def many_z(records: list[InputRecord]) -> list[InputRecord]:
    """The inputs whose ``s`` holds four ``"z"`` or more."""
    return [record for record in records if str(record.args["s"]).count("z") >= 4]


# llm-summary-input-run-again-at-a-no-fork-moment
def test_a_no_fork_moment_runs_the_seed_again_once_its_formula_is_in_use() -> None:
    done = encoded()

    assert len(before_checked(done)) == 1
    again = after_checked(done)[0]
    assert again.args == SEED
    assert (again.source, again.aim) == (Source.SUMMARY, None)
    [fork] = forks_at(again, line_of("encoded_z", "if t > 3:"))
    assert fork.expression == [">", Z, 3]


# llm-summary-input-run-again-at-a-5-input-moment
def test_a_5_input_moment_runs_again_the_latest_input_the_formula_was_checked_on() -> None:
    provider = FakeSummaries([COUNT])
    done = run_summaries(f"{LOOPS}::few_z", SEED, provider, LONGER)

    before = before_checked(done)
    assert len(before) >= 5
    again = after_checked(done)[0]
    assert again.args == before[-1].args
    assert (again.source, again.aim) == (Source.SUMMARY, None)


# llm-summary-input-not-run-again-for-a-formula-not-used
def test_a_formula_not_used_runs_no_input_again() -> None:
    done = encoded(Isolation.IN_PROCESS)

    assert any(" not used: " in line for line in done.llm_said()), done.said
    assert [record.source for record in done.records] == [Source.SEED]
    assert done.result.stopped.kind is StopKind.NO_FORK

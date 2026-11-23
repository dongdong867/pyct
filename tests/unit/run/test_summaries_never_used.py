"""A loop whose formula could never come into use is not asked about: one whose own code holds
a return, yield or await, and any loop while the run's inputs run in pyct's own process."""

from pyct.core.foundation.branch import PieceRun, Site
from pyct.results.causes import Condition, Reason, Source, SourceKind, WhyEntry
from pyct.results.coverage import Scope
from pyct.results.llm_asks import AskCost
from pyct.run.loops_in_use import IN_PYCT_S_PROCESS, never_used_because
from pyct.run.notes import Note, SummarySkipped
from pyct.run.stuck import Moment
from pyct.run.summaries import Summaries, SummaryReply
from pyct.run.target import load_target
from pyct.run.tell import Tell, Told
from tests.acceptance.harness import REPO_ROOT
from tests.unit.run.test_summaries import (
    LOOP,
    LOOPED,
    Fake,
    Run,
    counted,
    entry,
    one_thread,  # noqa: F401
    record,
)
from tests.unit.run.test_summaries_held_out import FORMULA

G = str(REPO_ROOT / "targets" / "summaries" / "loops.py")
FEW_STOPS = Site(G, 89, 4)
RETURNS = "the loop holds a return"


def test_a_loop_whose_own_code_returns_is_never_used() -> None:
    assert never_used_because(FEW_STOPS, isolated=True) == RETURNS


def test_no_loop_is_used_while_inputs_run_in_pyct_s_process() -> None:
    assert never_used_because(LOOP, isolated=False) == IN_PYCT_S_PROCESS


def test_a_loop_that_ends_by_its_own_test_can_be_used() -> None:
    assert never_used_because(LOOP, isolated=True) is None


def stopping(s: str) -> PieceRun:
    """A run of ``few_stops``'s loop on ``s``, one with no "!"."""
    run = counted(s)
    return PieceRun(FEW_STOPS, run.going_in, run.changed)


def test_a_loop_that_returns_is_not_asked_about_and_said_once_in_the_run() -> None:
    notes: list[Note] = []
    told = Told(scope=Scope.of_module(G), tell=Tell(noted=notes.append))
    fake = Fake(SummaryReply(FORMULA, AskCost(1)))
    tool = Summaries(
        fake, load_target("targets.summaries.loops::few_stops"), told, isolated=lambda: True
    )
    condition = Condition(Site(G, 94, 7), True)
    named = Source(SourceKind.LOOP, "t", FEW_STOPS)
    found = WhyEntry(G, (95,), Reason.NO_FORK, condition=condition, sources=(named,))
    run = Run([record(stopping("ab")), record(stopping("zz"))])

    first = tool.take((found,), Moment(1, (found,), run))
    tool.take((found,), Moment(2, (found,), run))

    assert fake.requests == []
    assert first.asked is False
    assert notes == [SummarySkipped(FEW_STOPS, RETURNS)]


def test_no_loop_is_asked_about_while_inputs_run_in_pyct_s_process() -> None:
    notes: list[Note] = []
    told = Told(scope=Scope.of_module(LOOP.file), tell=Tell(noted=notes.append))
    fake = Fake(SummaryReply(FORMULA, AskCost(1)))
    tool = Summaries(fake, load_target("targets.why.stuck::counts"), told, isolated=lambda: False)
    run = Run([record(counted("ab")), record(counted("zz"))])

    handled = tool.take((entry(LOOPED),), Moment(1, (), run))

    assert (fake.requests, handled.asked) == ([], False)
    assert notes == [SummarySkipped(LOOP, IN_PYCT_S_PROCESS)]

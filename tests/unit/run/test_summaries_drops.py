"""The summaries tool hears each input: a drop its record carries takes the loop out of use, says
why and leaves its state ``dropped``; once the run's inputs run in pyct's own process, each loop
in use goes out of use and is kept as checked."""

import pytest

from pyct.core.entry.in_use import IN_USE
from pyct.core.foundation.branch import DropReason, FormulaDrop, Site
from pyct.results.coverage import Scope
from pyct.results.llm_asks import AskCost, LoopSummary, SummaryState
from pyct.results.record import InputRecord
from pyct.run.loops_in_use import IN_PYCT_S_PROCESS
from pyct.run.notes import Note, SummaryDropped, SummaryNotUsed
from pyct.run.summaries import Summaries, SummaryReply
from pyct.run.target import load_target
from pyct.run.tell import Tell, Told
from tests.acceptance.llm_summaries import one_thread  # noqa: F401
from tests.unit.run.test_summaries import COUNTS, FILE, FORMULA, LOOP, Fake, counted, record

# `table` empties core's table of loops in use for each test and after it
from tests.unit.run.test_summaries_in_use import PLACE, table, taken, tool  # noqa: F401


def dropping(*drops: FormulaDrop) -> InputRecord:
    """The record of an input of six "z" whose run of the loop carries ``drops``."""
    pieces = (counted("zzzzzz"),)
    return InputRecord(args={}, forks=(), covered_lines=frozenset(), pieces=pieces, drops=drops)


@pytest.mark.parametrize(
    ("drop", "reason"),
    [
        (FormulaDrop(LOOP, "t", "5", "6", DropReason.MISMATCH), "t was 5, the formula gave 6"),
        (
            FormulaDrop(LOOP, "t", "5", '"6"', DropReason.MISMATCH),
            't was 5, the formula gave "6"',
        ),
        (
            FormulaDrop(LOOP, "t", "5", "ZeroDivisionError", DropReason.RAISED),
            "the formula raised ZeroDivisionError",
        ),
        (FormulaDrop(LOOP, "t", "5", "", DropReason.MISSING), "the formula gave no t"),
    ],
)
def test_a_drop_takes_the_loop_out_of_use_and_says_why(drop: FormulaDrop, reason: str) -> None:
    notes: list[Note] = []
    summaries, _ = tool(isolated=True, notes=notes)
    taken(summaries)
    notes.clear()

    summaries.heard(dropping(drop), 9)

    assert notes == [SummaryDropped(LOOP, 9, reason)]
    assert IN_USE == {}
    assert summaries.in_use.formulas == {}
    # the item keeps the formula, the tries and the runs of its check
    assert summaries.states() == (
        LoopSummary(FILE, 10, 4, ("t",), FORMULA, SummaryState.DROPPED, 1, 2),
    )


def test_an_input_with_no_drop_leaves_the_loop_in_use() -> None:
    notes: list[Note] = []
    summaries, _ = tool(isolated=True, notes=notes)
    taken(summaries)
    notes.clear()

    summaries.heard(record(counted("zzz")), 3)

    assert notes == []
    assert list(IN_USE) == [PLACE]
    assert summaries.states()[0].state is SummaryState.IN_USE


def test_a_drop_of_a_loop_no_longer_in_use_is_said_once() -> None:
    notes: list[Note] = []
    summaries, _ = tool(isolated=True, notes=notes)
    taken(summaries)
    notes.clear()
    drop = FormulaDrop(LOOP, "t", "5", "6", DropReason.MISMATCH)
    elsewhere = FormulaDrop(Site(FILE, 19, 11), "t", "5", "6", DropReason.MISMATCH)

    summaries.heard(dropping(drop, elsewhere), 9)
    summaries.heard(dropping(drop), 10)

    assert notes == [SummaryDropped(LOOP, 9, "t was 5, the formula gave 6")]


def test_inputs_that_fall_back_to_pyct_s_process_take_each_loop_out_of_use() -> None:
    notes: list[Note] = []
    isolated = [True]
    told = Told(scope=Scope.of_module(FILE), tell=Tell(noted=notes.append))
    fake = Fake(SummaryReply(FORMULA, AskCost(1)))
    summaries = Summaries(fake, load_target(COUNTS), told, isolated=lambda: isolated[0])
    taken(summaries)
    notes.clear()

    summaries.heard(record(counted("ab")), 8)
    assert list(IN_USE) == [PLACE]
    isolated[0] = False
    summaries.heard(record(counted("ab")), 9)
    summaries.heard(record(counted("ab")), 10)

    assert IN_USE == {}
    assert summaries.in_use.formulas == {}
    assert notes == [SummaryNotUsed(LOOP, IN_PYCT_S_PROCESS)]
    assert summaries.states()[0].state is SummaryState.CHECKED
    assert summaries.states()[0].checked_on == 2

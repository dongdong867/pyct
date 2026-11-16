"""A loop whose formula was dropped is asked about again when a later moment's entry names it: the
request holds the dropped formula among the earlier tries with why it was dropped, and the run it
failed on first among its runs, which the past-run check now also sees."""

import pytest

from pyct.core.foundation.branch import DropReason, FormulaDrop, Site
from pyct.results.coverage import Scope
from pyct.results.llm_asks import AskCost, SummaryState
from pyct.run.notes import Note, SummaryFailed
from pyct.run.stuck import Moment
from pyct.run.summaries import EarlierFormula, Summaries, SummaryReply
from pyct.run.summary_checks import CompleteRun
from pyct.run.summary_runs import AskedLoop, ShownRun, failed_run, piece_at, shown_runs
from pyct.run.target import load_target
from pyct.run.tell import Tell, Told
from tests.acceptance.llm_summaries import one_thread  # noqa: F401
from tests.unit.run.test_summaries import (
    COUNTS,
    FILE,
    FORMULA,
    LOOP,
    LOOPED,
    Fake,
    Run,
    counted,
    entry,
    record,
)
from tests.unit.run.test_summaries_drops import capped, dropping

# `table` empties core's table of loops in use for each test and after it
from tests.unit.run.test_summaries_in_use import table  # noqa: F401

DROP = FormulaDrop(LOOP, "t", "5", "6", DropReason.MISMATCH)


def test_the_same_wrong_formula_fails_on_the_run_it_was_dropped_at() -> None:
    notes: list[Note] = []
    told = Told(scope=Scope.of_module(FILE), tell=Tell(noted=notes.append))
    fake = Fake(SummaryReply(FORMULA, AskCost(1)))
    summaries = Summaries(fake, load_target(COUNTS), told, isolated=lambda: True)
    records = [record(counted("ab")), record(counted("zz"))]
    summaries.take((entry(LOOPED),), Moment(1, (), Run(records)))
    summaries.heard(dropping(DROP), 3)
    notes.clear()

    summaries.take((entry(LOOPED),), Moment(2, (), Run([*records, dropping(DROP)])))

    first, again = fake.requests
    why = "dropped at input 3: t was 5, the formula gave 6"
    assert again.tries == (EarlierFormula(FORMULA, why),)
    assert again.runs[0] == ShownRun((("s", '"zzzzzz"'), ("t", "0")), (("t", "5"),))
    assert first.runs[0] != again.runs[0]
    [failed] = [note for note in notes if isinstance(note, SummaryFailed)]
    assert failed.reason.startswith("at input 3, t was 5, the formula gave 6"), failed
    [state] = summaries.states()
    assert (state.state, state.checked_on) == (SummaryState.FAILED, None)


def test_the_run_a_drop_names_is_the_last_of_its_loop_with_the_loop_s_value() -> None:
    held = dropping(DROP).pieces[0]
    later = capped("ab")
    earlier = capped("zzzzzzz")

    found = failed_run(DROP, record(earlier, held, later), 9)

    assert found == CompleteRun(9, held)
    assert failed_run(DROP, record(later), 9) is None
    elsewhere = FormulaDrop(Site(FILE, 11, 4), "t", "5", "6", DropReason.MISMATCH)
    assert failed_run(elsewhere, record(held), 9) is None


@pytest.mark.parametrize("at", [0, 5, 11])
def test_the_run_a_formula_failed_on_comes_first_among_the_runs_shown(at: int) -> None:
    piece = piece_at(LOOP)
    assert piece is not None
    runs = tuple(CompleteRun(number, counted("z" * number)) for number in range(12))
    loop = AskedLoop(LOOP, piece, runs, ("s", "t"))

    shown = shown_runs(loop, runs[at])

    assert len(shown) == 10
    assert shown[0] == ShownRun((("s", f'"{"z" * at}"'), ("t", "0")), (("t", str(at)),))
    assert len(set(shown)) == 10

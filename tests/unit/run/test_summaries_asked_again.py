"""A loop whose formula was dropped is asked about again when a later moment's entry names it: the
request holds the dropped formula among the earlier tries with why it was dropped, and the run it
failed on first among its runs, which the past-run check now also sees. It keeps waiting, moment
after moment, until a formula of its is in use or checked."""

from collections.abc import Mapping
from dataclasses import replace

import pytest

from pyct.core.entry.in_use import IN_USE, LoopInUse
from pyct.core.foundation.branch import Changed, DropReason, FormulaDrop, PieceRun, Site
from pyct.core.strs.strs import ConcolicStr
from pyct.results.causes import Condition, Reason, WhyEntry
from pyct.results.coverage import Scope
from pyct.results.llm_asks import AskCost, SummaryState, Unanswered, Why
from pyct.results.record import InputRecord
from pyct.run.notes import Note, SummaryFailed
from pyct.run.stuck import Handled, Moment
from pyct.run.summaries import EarlierFormula, Summaries, SummaryReply
from pyct.run.summary_checks import CompleteRun
from pyct.run.summary_runs import AskedLoop, ShownRun, failed_run, piece_at, shown_runs
from pyct.run.target import load_target
from pyct.run.tell import Tell, Told
from tests.acceptance.llm_summaries import one_thread  # noqa: F401
from tests.unit.core.entry.test_in_use import using
from tests.unit.core.entry.test_pieces import hooked
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
from tests.unit.run.test_summaries_drops import dropping

# `table` empties core's table of loops in use for each test and after it
from tests.unit.run.test_summaries_in_use import table  # noqa: F401

DROP = FormulaDrop(LOOP, "t", "5", "6", DropReason.MISMATCH, run=0)


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


TWICE = """\
def count(s):
    t = 0
    for c in s:
        if c == "z" and t < 5:
            t += 1
    return t


def f(a, b):
    return count(a), count(b)
"""


def uncapped(values: Mapping[str, object]) -> Mapping[str, object]:
    s, t = values["s"], values["t"]
    assert isinstance(s, str)
    assert isinstance(t, int)
    return {"t": t + s.count("z")}


def test_the_run_a_drop_names_is_its_own_when_a_later_run_ends_with_the_same_value() -> None:
    f = hooked(TWICE)

    with using({(3, 4): LoopInUse(("s", "t"), ("t",), uncapped)}) as sink:
        f(ConcolicStr.made("zzzzzz", expression="a", sink=sink), "zzzzz")

    pieces = tuple(each for each in sink if type(each) is PieceRun)
    drops = tuple(each for each in sink if type(each) is FormulaDrop)
    record = InputRecord({}, (), frozenset(), pieces=pieces, drops=drops)
    # the formula gave 6 on six "z", then the loop, followed as written, counted five to 5
    [drop] = drops
    assert [each.changed for each in pieces] == [(Changed("t", "5"),)] * 2
    assert failed_run(drop, record, 4) == CompleteRun(4, pieces[0])


def test_a_drop_whose_run_is_not_in_the_record_names_none() -> None:
    held = dropping(DROP).pieces[0]

    assert failed_run(DROP, record(held), 9) == CompleteRun(9, held)
    assert failed_run(DROP, record(), 9) is None
    assert failed_run(replace(DROP, run=None), record(held), 9) is None
    elsewhere = FormulaDrop(Site(FILE, 11, 4), "t", "5", "6", DropReason.MISMATCH, run=0)
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


# `COUNT`'s count capped at 5, as the loop that dropped `FORMULA` counts
CAPPED = (
    'def summary(s, t):\n    t = t + s.count("z")\n    if t > 5:\n        t = 5\n'
    '    return {"t": t}\n'
)


def dropped_tool() -> tuple[Summaries, Fake]:
    """The tool for ``counts`` after its formula, asked for line 14, came into use and the
    input 3 dropped it."""
    told = Told(scope=Scope.of_module(FILE), tell=Tell())
    fake = Fake(SummaryReply(FORMULA, AskCost(1)))
    summaries = Summaries(fake, load_target(COUNTS), told, isolated=lambda: True)
    records = [record(counted("ab")), record(counted("zz"))]
    summaries.take((entry(LOOPED),), Moment(1, (entry(LOOPED),), Run(records)))
    summaries.heard(dropping(DROP), 3)
    return summaries, fake


def missed(*lines: int) -> tuple[WhyEntry, ...]:
    """A moment's causes: each line ``not taken``, which no ``no fork`` entry names."""
    condition = Condition(Site(FILE, 13, 7), True)
    return tuple(WhyEntry(FILE, (line,), Reason.NOT_TAKEN, condition=condition) for line in lines)


AFTER = [record(counted("ab")), record(counted("zz")), dropping(DROP), record(counted("ab"))]


def test_a_dropped_loop_is_asked_again_while_a_line_it_was_asked_for_is_missed() -> None:
    summaries, fake = dropped_tool()
    moment = Moment(2, missed(14), Run(AFTER))

    assert summaries.waiting(moment) is True
    handled = summaries.take((), moment)

    assert handled == Handled((), asked=True)
    assert len(fake.requests) == 2


def test_a_dropped_loop_whose_lines_are_covered_is_not_asked_again() -> None:
    summaries, fake = dropped_tool()
    moment = Moment(2, missed(15), Run(AFTER))

    assert summaries.waiting(moment) is False
    handled = summaries.take((), moment)

    assert handled == Handled((), asked=False)
    assert len(fake.requests) == 1
    assert summaries.states()[0].state is SummaryState.DROPPED


def test_a_dropped_loop_is_asked_once_at_a_moment_whose_entry_also_names_it() -> None:
    summaries, fake = dropped_tool()

    summaries.take((entry(LOOPED),), Moment(2, missed(14), Run(AFTER)))

    assert len(fake.requests) == 2


def test_a_dropped_loop_asked_again_whose_formula_passes_comes_into_use() -> None:
    summaries, fake = dropped_tool()
    fake.answer = SummaryReply(CAPPED, AskCost(2))

    summaries.take((), Moment(2, missed(14), Run(AFTER)))

    [state] = summaries.states()
    assert (state.state, state.formula, state.tries) == (SummaryState.IN_USE, CAPPED, 2)
    assert list(IN_USE) == [(FILE, 10, 4)]


def test_a_dropped_loop_is_not_asked_again_once_the_token_limit_is_reached() -> None:
    summaries, fake = dropped_tool()
    summaries.limit.reach()

    handled = summaries.take((), Moment(2, missed(14), Run(AFTER)))

    assert summaries.can_ask is False
    assert handled == Handled((), asked=False)
    assert len(fake.requests) == 1


@pytest.mark.parametrize(
    "first",
    [
        Unanswered(Why.TIMED_OUT, "no reply in 30 s", AskCost(2)),
        SummaryReply(FORMULA, AskCost(2)),
    ],
    ids=["no answer", "a failing formula"],
)
def test_a_dropped_loop_keeps_waiting_until_a_formula_of_its_is_in_use(
    first: SummaryReply | Unanswered,
) -> None:
    summaries, fake = dropped_tool()
    fake.answer = first

    summaries.take((), Moment(2, missed(14), Run(AFTER)))
    waits = summaries.waiting(Moment(3, missed(14), Run(AFTER)))
    fake.answer = SummaryReply(CAPPED, AskCost(3))
    summaries.take((), Moment(3, missed(14), Run(AFTER)))

    assert waits is True
    assert len(fake.requests) == 3
    [state] = summaries.states()
    assert (state.state, state.formula) == (SummaryState.IN_USE, CAPPED)
    assert summaries.waiting(Moment(4, missed(14), Run(AFTER))) is False

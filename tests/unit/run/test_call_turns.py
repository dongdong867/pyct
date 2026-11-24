"""A loss site's checked formula comes into use when the run's inputs run in a process of their
own: core's table holds it under its downgrade's name and positions, and the input its check used
runs again after the turn. Inputs in pyct's own process skip the site with no ask, and a fall-back
to pyct's own process takes each site out of use, kept as checked. Given records made by hand."""

import dataclasses
import json
from collections.abc import Iterator

import pytest

from pyct.core.entry.calls_in_use import CALLS_IN_USE
from pyct.core.foundation.branch import (
    Changed,
    DropReason,
    FormulaDrop,
    GoingIn,
    LossRun,
    PieceRun,
    Site,
)
from pyct.results.coverage import Scope
from pyct.results.llm_asks import SummaryState
from pyct.results.record import InputRecord
from pyct.results.record import Source as RecordSource
from pyct.run.formula_runner import FormulaRunner
from pyct.run.loops_in_use import kinds_unused_because
from pyct.run.notes import Note, SummaryDropped, SummaryNotUsed, SummarySkipped
from pyct.run.stuck import Outcome
from pyct.run.summaries import EarlierFormula, Summaries
from pyct.run.summary_checks import CompleteRun
from pyct.run.target import load_target
from pyct.run.tell import Tell, Told
from tests.unit.run.test_summaries_calls import (
    FILE,
    QUARTER,
    Fake,
    heard,
    lost_at,
    moment_of,
    one_thread,  # noqa: F401
    record,
    shift,
)

IN_PYCT_S_PROCESS = "inputs run in pyct's own process"
SITE = Site(FILE, 37, 8)


@pytest.fixture(autouse=True)
def table() -> Iterator[None]:
    """Core's table of loss sites in use, empty for the test and after it."""
    CALLS_IN_USE.clear()
    yield
    CALLS_IN_USE.clear()


class Isolated:
    """Whether the run's inputs run in a process of their own, which a test can change."""

    def __init__(self) -> None:
        self.now = True

    def __call__(self) -> bool:
        return self.now


def tool(fake: Fake, notes: list[Note], isolated: Isolated | None = None) -> Summaries:
    told = Told(scope=Scope.of_module(FILE), tell=Tell(noted=notes.append))
    target = load_target("targets.summaries.calls::deep")
    return Summaries(fake, target, told, isolated=isolated or Isolated())


def test_a_checked_formula_comes_into_use_under_its_name_and_positions() -> None:
    fake, notes = Fake(), []
    summaries = tool(fake, notes)

    summaries.between(heard(summaries, [record(shift(37, 8, 13, 2))]))

    [state] = summaries.states()
    assert (state.kind, state.state, state.checked_on) == ("call", SummaryState.IN_USE, 1)
    call = CALLS_IN_USE[(FILE, 37, 8)]
    assert (call.name, call.positions) == ("__rshift__", ("n", None))
    assert isinstance(call.formula, FormulaRunner)
    text = call.formula.text
    assert (text.text, text.parameters, text.changed) == (QUARTER, ("n",), ("answer",))
    assert (text.name, text.positions, text.place) == ("__rshift__", ("n", None), (FILE, 37, 8))
    assert notes[-1] != SummaryNotUsed(SITE, IN_PYCT_S_PROCESS, call="__rshift__")


def test_the_input_its_check_used_runs_again_once_labeled_summary() -> None:
    fake, notes = Fake(), []
    summaries = tool(fake, notes)
    first = record(shift(37, 8, 13, 2))
    second = dataclasses.replace(record(shift(37, 8, 21, 2)), args={"n": 21})
    run = heard(summaries, [first, second])

    summaries.between(run)
    summaries.run_again(run)
    summaries.run_again(run)

    assert [(seed.args, source, plan) for seed, source, plan in run.ran] == [
        ({"n": 21}, RecordSource.SUMMARY, None)
    ]


def test_a_site_in_use_is_not_asked_about_again_and_its_entry_is_taken() -> None:
    fake, notes = Fake(), []
    summaries = tool(fake, notes)
    run = heard(summaries, [record(shift(37, 8, 13, 2))])
    summaries.between(run)

    summaries.between(heard(summaries, [record(shift(37, 8, 13, 2))] * 2))

    assert len(fake.requests) == 1
    assert moment_of(summaries, run, lost_at(37, 8)) == (Outcome.TOOK,)


def test_inputs_in_pyct_s_own_process_skip_the_site_with_no_ask_said_once() -> None:
    fake, notes = Fake(), []
    isolated = Isolated()
    isolated.now = False
    summaries = tool(fake, notes, isolated)

    summaries.between(heard(summaries, [record(shift(37, 8, 13, 2))]))
    summaries.between(heard(summaries, [record(shift(38, 8, 13, 3))]))

    assert fake.requests == []
    assert notes == [
        SummarySkipped(SITE, IN_PYCT_S_PROCESS, call="__rshift__"),
        SummarySkipped(Site(FILE, 38, 8), IN_PYCT_S_PROCESS, call="__rshift__"),
    ]
    assert CALLS_IN_USE == {}


def test_a_fall_back_to_pyct_s_own_process_takes_each_site_out_of_use_kept_checked() -> None:
    fake, notes = Fake(), []
    isolated = Isolated()
    summaries = tool(fake, notes, isolated)
    summaries.between(heard(summaries, [record(shift(37, 8, 13, 2))]))
    assert set(CALLS_IN_USE) == {(FILE, 37, 8)}

    isolated.now = False
    summaries.heard(record(shift(37, 8, 13, 2)), 2)
    summaries.heard(record(shift(37, 8, 13, 2)), 3)

    assert CALLS_IN_USE == {}
    [state] = summaries.states()
    assert state.state is SummaryState.CHECKED
    assert notes.count(SummaryNotUsed(SITE, IN_PYCT_S_PROCESS, call="__rshift__")) == 1


def test_the_run_s_end_takes_each_site_out_of_core_s_table() -> None:
    fake, notes = Fake(), []
    summaries = tool(fake, notes)
    summaries.between(heard(summaries, [record(shift(37, 8, 13, 2))]))

    summaries.close()

    assert CALLS_IN_USE == {}


def answered(text: str) -> CompleteRun:
    return CompleteRun(1, PieceRun(SITE, (), (Changed("answer", text),)))


def test_a_formula_whose_runs_recorded_an_answer_of_another_kind_is_not_used() -> None:
    runs = [answered("3"), answered(json.dumps([1])), answered("null")]

    assert kinds_unused_because(runs[:1], ("answer",)) is None
    assert kinds_unused_because(runs[:2], ("answer",)) == "answer is a list"
    assert kinds_unused_because(runs[2:], ("answer",)) == "answer is None"


def dropped_by(drop: FormulaDrop, *runs: LossRun) -> InputRecord:
    return dataclasses.replace(record(*runs), drops=(drop,))


@pytest.mark.parametrize(
    ("drop", "reason"),
    [
        pytest.param(
            FormulaDrop(SITE, "answer", "5", "6", DropReason.MISMATCH, run=1),
            "answer was 5, the formula gave 6",
            id="a mismatch",
        ),
        pytest.param(
            FormulaDrop(SITE, "answer", "5", "ZeroDivisionError", DropReason.RAISED, run=1),
            "the formula raised ZeroDivisionError",
            id="a raise",
        ),
        pytest.param(
            FormulaDrop(SITE, "answer", "5", "", DropReason.MISSING, run=1),
            "the formula gave no answer",
            id="no answer",
        ),
    ],
)
def test_an_input_s_drop_takes_the_site_out_of_use_and_says_why(
    drop: FormulaDrop, reason: str
) -> None:
    fake, notes = Fake(), []
    summaries = tool(fake, notes)
    summaries.between(heard(summaries, [record(shift(37, 8, 13, 2))]))

    summaries.heard(dropped_by(drop, shift(37, 8, 9, 2), shift(37, 8, 21, 2)), 2)
    summaries.heard(record(shift(37, 8, 13, 2)), 3)

    assert CALLS_IN_USE == {}
    assert notes[-1] == SummaryDropped(SITE, 2, reason, call="__rshift__")
    assert notes.count(notes[-1]) == 1
    [state] = summaries.states()
    assert state.state is SummaryState.DROPPED
    kept = summaries.loops[SITE]
    assert kept.tries == [EarlierFormula(QUARTER, f"dropped at input 2: {reason}")]
    assert kept.failed_on == CompleteRun(
        2,
        PieceRun(SITE, (GoingIn("n", "21", tracked=True),), (Changed("answer", "5"),)),
    )


def test_a_drop_whose_run_was_not_recorded_keeps_no_failing_run() -> None:
    fake, notes = Fake(), []
    summaries = tool(fake, notes)
    summaries.between(heard(summaries, [record(shift(37, 8, 13, 2))]))
    drop = FormulaDrop(SITE, "answer", "5", "6", DropReason.MISMATCH)

    summaries.heard(dropped_by(drop, shift(37, 8, 9, 2)), 2)

    assert summaries.loops[SITE].failed_on is None
    assert summaries.loops[SITE].last is SummaryState.DROPPED


def test_a_drop_at_a_site_not_in_use_changes_nothing() -> None:
    fake, notes = Fake(), []
    summaries = tool(fake, notes)
    drop = FormulaDrop(Site(FILE, 38, 8), "answer", "5", "6", DropReason.MISMATCH, run=0)

    summaries.heard(dropped_by(drop, shift(38, 8, 9, 3)), 1)

    assert not [note for note in notes if isinstance(note, SummaryDropped)]

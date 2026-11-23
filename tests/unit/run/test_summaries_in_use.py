"""The summaries tool puts a formula that passed both checks in use when the run's inputs run in a
process of their own, keeps it checked when they run in pyct's, does not ask about a loop in use
again, and takes its loops out of use as the run ends."""

import dataclasses
from collections.abc import Iterator

import pytest

from pyct.core.entry import in_use
from pyct.core.entry.in_use import LoopInUse
from pyct.results.coverage import Scope
from pyct.results.llm_asks import AskCost, LoopSummary, SummaryState
from pyct.results.record import Source as RecordSource
from pyct.run import loop
from pyct.run.formula_runner import FormulaRunner
from pyct.run.helpers import Helpers
from pyct.run.isolation import Isolation
from pyct.run.loops_in_use import IN_PYCT_S_PROCESS
from pyct.run.notes import Note, SummaryChecked, SummaryNotUsed, SummaryRead
from pyct.run.run import run
from pyct.run.setup import Setup
from pyct.run.stuck import Handled, Moment, Outcome
from pyct.run.summaries import Summaries, SummaryReply
from pyct.run.target import load_target
from pyct.run.tell import Tell, Told
from tests.acceptance.llm_summaries import (
    COUNT,
    SEED,
    FakeSummaries,
    one_thread,  # noqa: F401
    run_summaries,
)
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

PLACE = (FILE, 10, 4)
FEW_Z = "targets.summaries.loops::few_z"


@pytest.fixture(autouse=True)
def table() -> Iterator[dict[tuple[str, int, int], LoopInUse]]:
    """Core's table of loops in use, empty for the test and after it."""
    in_use.IN_USE.clear()
    yield in_use.IN_USE
    in_use.IN_USE.clear()


def tool(isolated: bool, notes: list[Note] | None = None) -> tuple[Summaries, Fake]:
    """The tool for ``counts``, its provider answering ``FORMULA``, told whether the run's inputs
    run in a process of their own."""
    told = Told(
        scope=Scope.of_module(FILE), tell=Tell(noted=(notes if notes is not None else []).append)
    )
    fake = Fake(SummaryReply(FORMULA, AskCost(1)))
    return Summaries(fake, load_target(COUNTS), told, isolated=lambda: isolated), fake


def taken(summaries: Summaries, at: int = 1) -> Handled:
    run = Run([record(counted("ab")), record(counted("zz"))])
    return summaries.take((entry(LOOPED),), Moment(at, (), run))


def test_a_formula_that_passes_comes_into_use_for_inputs_in_a_process_of_their_own(
    table: dict[tuple[str, int, int], LoopInUse],
) -> None:
    notes: list[Note] = []
    summaries, _ = tool(isolated=True, notes=notes)

    handled = taken(summaries)

    assert handled == Handled((Outcome.TOOK,), asked=True)
    assert notes == [SummaryRead(LOOP, 't = t + s.count("z")'), SummaryChecked(LOOP, 2)]
    assert summaries.states() == (
        LoopSummary(FILE, 10, 4, ("t",), FORMULA, SummaryState.IN_USE, 1, 2),
    )
    assert list(table) == [PLACE]
    assert (table[PLACE].parameters, table[PLACE].changed) == (("s", "t"), ("t",))
    assert summaries.in_use.sites == {LOOP}
    runner = table[PLACE].formula
    assert isinstance(runner, FormulaRunner)
    assert (runner.text.text, runner.text.place, runner.text.file) == (
        FORMULA,
        PLACE,
        "<summary targets.why.stuck:10:4>",
    )


def test_a_formula_put_in_use_runs_again_the_latest_input_it_was_checked_on() -> None:
    summaries, _ = tool(isolated=True)
    records = [
        dataclasses.replace(record(counted("ab")), args={"s": "ab"}),
        dataclasses.replace(record(counted("zz")), args={"s": "zz"}),
        dataclasses.replace(record(), args={"s": "no run of the loop"}),
    ]
    run = Run(records)

    summaries.take((entry(LOOPED),), Moment(1, (), run))

    assert [(seed.args, source, wanted) for seed, source, wanted in run.ran] == [
        ({"s": "zz"}, RecordSource.SUMMARY, None)
    ]
    assert summaries.again == []


def test_a_formula_not_put_in_use_runs_no_input_again() -> None:
    summaries, _ = tool(isolated=False)
    run = Run([dataclasses.replace(record(counted("zz")), args={"s": "zz"})])

    summaries.take((entry(LOOPED),), Moment(1, (), run))

    assert run.ran == []


def test_a_loop_in_use_runs_no_input_again_at_a_later_moment() -> None:
    summaries, _ = tool(isolated=True)
    run = Run([dataclasses.replace(record(counted("zz")), args={"s": "zz"})])
    summaries.take((entry(LOOPED),), Moment(1, (), run))

    summaries.take((entry(LOOPED),), Moment(2, (), run))

    assert len(run.ran) == 1


def test_a_formula_that_passes_stays_checked_for_inputs_in_pyct_s_process(
    table: dict[tuple[str, int, int], LoopInUse],
) -> None:
    summaries, _ = tool(isolated=False)

    handled = taken(summaries)

    assert handled == Handled((Outcome.TOOK,), asked=True)
    assert summaries.states() == (
        LoopSummary(FILE, 10, 4, ("t",), FORMULA, SummaryState.CHECKED, 1, 2),
    )
    assert table == {}


def test_a_formula_not_used_says_why_right_after_its_checked_line() -> None:
    notes: list[Note] = []
    summaries, _ = tool(isolated=False, notes=notes)

    taken(summaries)

    assert notes == [
        SummaryRead(LOOP, 't = t + s.count("z")'),
        SummaryChecked(LOOP, 2),
        SummaryNotUsed(LOOP, IN_PYCT_S_PROCESS),
    ]


def test_a_formula_not_used_is_said_once_and_its_loop_not_asked_about_again() -> None:
    notes: list[Note] = []
    summaries, fake = tool(isolated=False, notes=notes)
    taken(summaries)

    handled = taken(summaries, at=2)

    assert len(fake.requests) == 1
    assert handled == Handled((Outcome.TOOK,), asked=False)
    assert [each for each in notes if isinstance(each, SummaryNotUsed)] == [
        SummaryNotUsed(LOOP, IN_PYCT_S_PROCESS)
    ]
    assert summaries.states()[0].state is SummaryState.CHECKED


def test_a_loop_in_use_is_not_asked_about_again() -> None:
    summaries, fake = tool(isolated=True)
    taken(summaries)

    handled = taken(summaries, at=2)

    assert len(fake.requests) == 1
    assert handled == Handled((Outcome.TOOK,), asked=False)
    assert summaries.states()[0].state is SummaryState.IN_USE


def test_closing_takes_the_run_s_loops_out_of_use(
    table: dict[tuple[str, int, int], LoopInUse],
) -> None:
    summaries, _ = tool(isolated=True)
    taken(summaries)

    summaries.close()

    assert table == {}
    assert summaries.in_use.sites == set()
    # the summary line still says what came of the ask
    assert summaries.states()[0].state is SummaryState.IN_USE


def test_the_run_takes_its_loops_out_of_use_when_it_ends(
    table: dict[tuple[str, int, int], LoopInUse],
) -> None:
    provider = FakeSummaries([COUNT])

    done = run_summaries(FEW_Z, SEED, provider)

    assert [each.state for each in done.result.summaries] == [SummaryState.IN_USE]
    assert table == {}


def test_a_run_that_raises_takes_its_loops_out_of_use(monkeypatch: pytest.MonkeyPatch) -> None:
    closed: list[Summaries] = []

    def broken(self: loop.Loop, starts: object) -> object:
        raise RuntimeError("boom")

    monkeypatch.setattr(loop.Loop, "go", broken)
    monkeypatch.setattr(Summaries, "close", lambda self: closed.append(self))
    setup = Setup(isolation=Isolation.FORK, helpers=Helpers(summaries=Fake()))

    with pytest.raises(RuntimeError, match="boom"):
        run(load_target(COUNTS), {"s": "ab"}, setup=setup)

    assert len(closed) == 1

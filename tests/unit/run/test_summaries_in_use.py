"""The summaries tool puts a formula that passed both checks in use when the run's inputs run in a
process of their own, keeps it checked when they run in pyct's, does not ask about a loop in use
again, and takes its loops out of use as the run ends."""

from collections.abc import Iterator

import pytest

from pyct.core.entry import in_use
from pyct.core.entry.in_use import LoopInUse
from pyct.results.coverage import Scope
from pyct.results.llm_asks import AskCost, LoopSummary, SummaryState
from pyct.run import loop
from pyct.run.helpers import Helpers
from pyct.run.isolation import Isolation
from pyct.run.loops_in_use import FormulaInUse
from pyct.run.notes import Note, SummaryChecked, SummaryRead
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
    [formula] = summaries.in_use.formulas.values()
    assert (formula.text, formula.site, formula.file) == (
        FORMULA,
        LOOP,
        "<summary targets.why.stuck:10:4>",
    )
    assert isinstance(formula, FormulaInUse)


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
    assert summaries.in_use.formulas == {}
    # the summary line still says what came of the ask
    assert summaries.states()[0].state is SummaryState.IN_USE


def test_a_tool_told_nothing_of_where_inputs_run_keeps_a_formula_checked(
    table: dict[tuple[str, int, int], LoopInUse],
) -> None:
    told = Told(scope=Scope.of_module(FILE), tell=Tell())
    summaries = Summaries(Fake(SummaryReply(FORMULA, AskCost(1))), load_target(COUNTS), told)

    taken(summaries)

    assert summaries.states()[0].state is SummaryState.CHECKED
    assert table == {}


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

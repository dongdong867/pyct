"""The summaries tool's turn between passes: it notes each loss site an input first records a run
of, and asks about each once per run, in the order noted, while it can still ask, skipping the
sites a formula cannot stand for; given records made by hand."""

import ast
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any

import pytest

from pyct.core.entry.in_use import CALLS_IN_USE
from pyct.core.foundation.branch import Changed, GoingIn, LossKind, LossRun, Site
from pyct.results.causes import Condition, Reason, Source, SourceKind, WhyEntry
from pyct.results.coverage import Scope
from pyct.results.llm_asks import AskCost, SummaryState
from pyct.results.record import InputRecord, Stop, StopKind
from pyct.run import model_runs
from pyct.run.notes import Note, SummarySkipped
from pyct.run.stuck import Moment, Outcome
from pyct.run.summaries import Summaries
from pyct.run.summary_asks import SummaryReply, SummaryRequest
from pyct.run.target import load_target
from pyct.run.tell import Tell, Told
from pyct.run.token_limit import TokenLimit
from tests.unit.run.test_summaries import Run

FILE = load_target("targets.summaries.calls::deep").file
QUARTER = 'def summary(n):\n    return {"answer": n % 4}\n'


def shift(line: int, col: int, n: int, by: int, name: str = "__pow__") -> LossRun:
    """A run of ``pow(n, 1, 2**by)`` at the line and column of ``calls.py``."""
    going_in = (
        GoingIn("arg1", str(n), tracked=True),
        GoingIn("arg2", "1", tracked=False),
        GoingIn("arg3", str(2**by), tracked=False),
    )
    return LossRun(
        Site(FILE, line, col),
        name,
        LossKind.OPERATION,
        going_in,
        (Changed("answer", str(n % 2**by)),),
    )


def record(*runs: LossRun) -> InputRecord:
    return InputRecord(args={"n": 3}, forks=(), covered_lines=frozenset(), losses=runs)


DEEP = record(shift(36, 8, 3, 1), shift(37, 8, 3, 2), shift(38, 8, 3, 3), shift(40, 11, 3, 4))


@dataclass
class Fake:
    """Answers each ask with ``code``, its cost leaving ``left`` tokens, and keeps each request."""

    code: str = QUARTER
    left: int | None = None
    requests: list[SummaryRequest] = field(default_factory=list)

    def summarize(self, request: SummaryRequest) -> SummaryReply:
        self.requests.append(request)
        return SummaryReply(self.code, AskCost(1, 10, 10, tokens_left=self.left))


@pytest.fixture(autouse=True)
def one_thread(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """pyct's process as a run has it, one thread, and core's table of loss sites in use empty
    after the test, since a formula that passes comes into use."""
    monkeypatch.setattr(model_runs, "running", lambda: 1)
    yield
    CALLS_IN_USE.clear()


def tool(fake: Fake, notes: list[Note], limit: TokenLimit | None = None) -> Summaries:
    told = Told(scope=Scope.of_module(FILE), tell=Tell(noted=notes.append))
    target = load_target("targets.summaries.calls::deep")
    return Summaries(fake, target, told, limit, isolated=lambda: True)


def heard(summaries: Summaries, records: Sequence[InputRecord]) -> Run:
    for number, each in enumerate(records, start=1):
        summaries.heard(each, number)
    return Run(records)


def lines(fake: Fake) -> list[str]:
    return [request.place.rsplit(":", 2)[1] for request in fake.requests]


def test_each_site_an_input_recorded_is_asked_about_once_in_the_order_recorded() -> None:
    fake, notes = Fake(), []
    summaries = tool(fake, notes)

    run = heard(summaries, [DEEP])
    summaries.between(run)
    summaries.between(heard(summaries, [DEEP, DEEP]))

    assert lines(fake) == ["36", "37", "38", "40"]
    assert len(run.paused) == 4


def test_a_site_a_later_input_first_records_is_asked_about_at_the_next_turn() -> None:
    fake, notes = Fake(), []
    summaries = tool(fake, notes)
    first = record(shift(36, 8, 3, 1))

    summaries.between(heard(summaries, [first]))
    summaries.between(heard(summaries, [first, record(shift(38, 8, 9, 3))]))

    assert lines(fake) == ["36", "38"]


def test_no_ask_starts_once_the_token_limit_is_reached() -> None:
    fake, notes = Fake(left=0), []
    limit = TokenLimit()
    summaries = tool(fake, notes, limit)

    summaries.between(heard(summaries, [DEEP]))

    assert lines(fake) == ["36"]
    assert limit.reached
    assert not summaries.can_ask


def test_no_ask_starts_once_the_run_met_a_stop() -> None:
    fake, notes = Fake(), []
    summaries = tool(fake, notes)
    run = heard(summaries, [DEEP])
    run.stopped = Stop(StopKind.BUDGET)

    summaries.between(run)

    assert fake.requests == []


def test_a_checked_formula_is_kept_with_its_name() -> None:
    fake, notes = Fake(), []
    summaries = tool(fake, notes)

    summaries.between(heard(summaries, [record(shift(37, 8, 13, 2))]))

    [state] = summaries.states()
    assert (state.kind, state.name, state.state, state.checked_on) == (
        "call",
        "__pow__",
        SummaryState.IN_USE,
        1,
    )
    assert (state.line, state.col, state.changes, state.formula) == (37, 8, ("answer",), QUARTER)


@pytest.mark.parametrize(
    ("run", "reason"),
    [
        pytest.param(shift(37, 8, 3, 2, "__index__"), "Python converts its answer", id="converts"),
        pytest.param(
            LossRun(
                Site(FILE, 37, 8),
                "f",
                LossKind.CALL,
                (GoingIn("arg1", "3", tracked=True),),
                (Changed("answer", "[1]"),),
            ),
            "the answer is a list",
            id="a list",
        ),
    ],
)
def test_a_site_a_formula_cannot_stand_for_is_skipped_and_said_once(
    run: LossRun, reason: str
) -> None:
    fake, notes = Fake(), []
    summaries = tool(fake, notes)

    summaries.between(heard(summaries, [record(run)]))
    summaries.between(heard(summaries, [record(run), record(run)]))

    assert fake.requests == []
    assert notes == [SummarySkipped(run.site, reason, call=run.name)]


def test_a_site_is_skipped_while_pyct_s_process_runs_a_second_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(model_runs, "running", lambda: 2)
    fake, notes = Fake(), []
    summaries = tool(fake, notes)
    run = shift(37, 8, 3, 2)

    summaries.between(heard(summaries, [record(run)]))

    assert fake.requests == []
    assert notes == [SummarySkipped(run.site, "cannot fork", call="__pow__")]


def moment_of(summaries: Summaries, run: Run, *entries: WhyEntry) -> tuple[Outcome, ...]:
    return summaries.take(entries, Moment(1, entries, run)).outcomes


def lost_at(line: int, col: int) -> WhyEntry:
    """An entry whose condition reads the value lost at the shift at the line and column."""
    lost = Source(SourceKind.LOST, "n", Site(FILE, line, col), call="__pow__")
    condition = Condition(Site(FILE, 41, 7), True)
    return WhyEntry(FILE, (42,), Reason.NO_FORK, condition=condition, sources=(lost,))


NO_SOURCE = WhyEntry(FILE, (42,), Reason.NO_FORK, condition=Condition(Site(FILE, 41, 7), True))


def test_an_entry_whose_lost_sites_are_checked_is_taken_and_no_ask_is_sent() -> None:
    fake, notes = Fake(), []
    summaries = tool(fake, notes)
    run = heard(summaries, [record(shift(36, 8, 13, 2), shift(37, 8, 13, 2))])
    summaries.between(run)

    outcomes = moment_of(summaries, run, lost_at(36, 8), NO_SOURCE)

    assert outcomes == (Outcome.TOOK, Outcome.GAVE_UP)
    assert len(fake.requests) == 2


def test_an_entry_whose_lost_site_failed_or_was_skipped_is_given_up() -> None:
    fake, notes = Fake(), []
    summaries = tool(fake, notes)
    run = heard(summaries, [record(shift(36, 8, 3, 1), shift(37, 8, 3, 2, "__index__"))])
    summaries.between(run)

    outcomes = moment_of(summaries, run, lost_at(36, 8), lost_at(37, 8))

    assert outcomes == (Outcome.GAVE_UP, Outcome.GAVE_UP)


def test_an_entry_is_skipped_while_a_loss_site_waits_for_its_turn() -> None:
    fake, notes = Fake(), []
    summaries = tool(fake, notes)
    run = heard(summaries, [record(shift(36, 8, 3, 1))])

    outcomes = moment_of(summaries, run, lost_at(36, 8), NO_SOURCE)

    assert outcomes == (Outcome.SKIPPED, Outcome.SKIPPED)
    assert fake.requests == []


def test_a_run_parses_the_file_of_its_loss_sites_once(monkeypatch: pytest.MonkeyPatch) -> None:
    fake, notes = Fake(), []
    summaries = tool(fake, notes)
    parse = ast.parse
    parsed: list[str] = []

    def counted(source: str, filename: str = "<unknown>", *args: Any, **kwargs: Any) -> Any:
        parsed.append(filename)
        return parse(source, filename, *args, **kwargs)

    monkeypatch.setattr(ast, "parse", counted)

    summaries.between(heard(summaries, [DEEP]))

    assert len(fake.requests) == 4
    assert parsed.count(FILE) == 1

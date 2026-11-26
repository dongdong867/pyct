"""The summaries tool's ask about a loss site and what a stuck moment hands back: the runs an ask
shows, how its reply is read and checked, what the summary line lists for the site, and the
outcome of each entry, given records made by hand."""

import time
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from pyct.binding.bind import Seed
from pyct.branches.plan import Plan
from pyct.core.entry.in_use import CALLS_IN_USE
from pyct.core.foundation.branch import (
    Changed,
    DropReason,
    FormulaDrop,
    GoingIn,
    LossKind,
    LossRun,
    Site,
)
from pyct.results.causes import Condition, Reason, Source, SourceKind, WhyEntry
from pyct.results.coverage import Scope
from pyct.results.llm_asks import AskCost, SiteSummary, SummaryState, Unanswered, Why
from pyct.results.record import InputRecord, Stop
from pyct.results.record import Source as RecordSource
from pyct.run import call_summaries, model_runs, summaries
from pyct.run.bounds import Bounds
from pyct.run.call_summaries import AskedCall
from pyct.run.notes import (
    AskSkipped,
    Note,
    SummaryChecked,
    SummaryFailed,
    SummaryRead,
    SummarySkipped,
)
from pyct.run.stuck import Handled, Moment, Outcome
from pyct.run.summaries import EarlierFormula, Summaries, SummaryReply, SummaryRequest
from pyct.run.summary_checks import AskedRun, CompleteRun
from pyct.run.summary_outcomes import SiteState
from pyct.run.summary_runs import ShownRun, shown_runs
from pyct.run.target import load_target
from pyct.run.tell import Ask, Tell, Told
from tests.acceptance.harness import REPO_ROOT

FILE = str(REPO_ROOT / "targets" / "summaries" / "calls.py")
SHIFTED = "targets.summaries.calls::shifted"
# `pow(n, 1, 4)` in `_quarter`, which `shifted` calls
SITE = Site(FILE, 11, 11)
STUCK = str(REPO_ROOT / "targets" / "why" / "stuck.py")
LOOP = Site(STUCK, 10, 4)
CALL = Site(STUCK, 26, 7)
COUNTS = "targets.why.stuck::counts"
QUARTER = 'def summary(n):\n    return {"answer": n % 4}\n'
WRONG = 'def summary(n):\n    return {"answer": n * n}\n'


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


def quartered(n: int) -> LossRun:
    """A run of the site `SITE` on ``n``."""
    return shift(SITE.line, SITE.col, n, 2)


def record(*runs: LossRun) -> InputRecord:
    return InputRecord(args={"n": 3}, forks=(), covered_lines=frozenset(), losses=runs)


def entry(*sources: Source, line: int = 14) -> WhyEntry:
    condition = Condition(Site(STUCK, line - 1, 7), True)
    return WhyEntry(STUCK, (line,), Reason.NO_FORK, condition=condition, sources=sources)


LOOPED = Source(SourceKind.LOOP, "t", LOOP)
# an entry whose condition reads the answer of the site `SITE`
LOST = WhyEntry(
    FILE,
    (16,),
    Reason.NO_FORK,
    condition=Condition(Site(FILE, 15, 7), True),
    sources=(Source(SourceKind.LOST, "k", SITE, call="__pow__"),),
)


@dataclass
class Run:
    """The run as a moment sees it, its records made by hand. It keeps each input a tool runs,
    with its source, and adds none to its records."""

    records: Sequence[InputRecord]
    bounds: Bounds = field(default_factory=Bounds)
    stopped: Stop | None = None
    paused: list[float] = field(default_factory=list)
    ran: list[tuple[Seed, RecordSource, Plan | None]] = field(default_factory=list)

    def causes(self, stop_at: float | None) -> tuple[WhyEntry, ...]:
        return ()

    def run_input(
        self, seed: Seed, source: RecordSource, wanted: Plan | None = None
    ) -> InputRecord | Stop:
        self.ran.append((seed, source, wanted))
        return InputRecord(args=seed.args, forks=(), covered_lines=frozenset(), source=source)

    def tell_ask(self, ask: Ask) -> None:
        raise AssertionError("summaries ask no solver")

    def pause(self, seconds: float) -> None:
        self.paused.append(seconds)


@dataclass
class Fake:
    """Answers each ask with ``answer`` and keeps each request."""

    answer: SummaryReply | Unanswered = SummaryReply("", AskCost(1), ignored="no code block")
    requests: list[SummaryRequest] = field(default_factory=list)

    def summarize(self, request: SummaryRequest) -> SummaryReply | Unanswered:
        self.requests.append(request)
        return self.answer


@pytest.fixture(autouse=True)
def one_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(model_runs, "running", lambda: 1)


@pytest.fixture(autouse=True)
def no_site_in_use() -> Iterator[None]:
    """Core's table of loss sites in use, empty after the test, since a formula that passes here
    comes into use."""
    yield
    CALLS_IN_USE.clear()


def apart() -> bool:
    """Where a tool built here is told the run's inputs run: each in a process of its own, so
    that summaries ask about a loss site and a formula that passes comes into use."""
    return True


def tool_of(fake: Fake, notes: list[Note], spec: str = SHIFTED) -> Summaries:
    told = Told(scope=Scope.of_module(FILE), tell=Tell(noted=notes.append))
    return Summaries(fake, load_target(spec), told, isolated=apart)


def turned(fake: Fake, run: Run) -> tuple[Summaries, list[Note]]:
    """A tool that heard each of the run's records, then gave its loss sites their turn."""
    notes: list[Note] = []
    tool = tool_of(fake, notes)
    for number, each in enumerate(run.records, start=1):
        tool.heard(each, number)
    tool.between(run)
    return tool, notes


def taken(tool: Summaries, run: Run, *entries: WhyEntry) -> Handled:
    return tool.take(entries, Moment(1, entries, run))


def listed(
    formula: str | None, state: SummaryState, tries: int, checked_on: int | None = None
) -> tuple[SiteSummary, ...]:
    """The site `SITE` as the summary line lists it."""
    return (SiteSummary("__pow__", FILE, 11, 11, ("answer",), formula, state, tries, checked_on),)


def test_the_clock_pauses_for_the_model_s_wait_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    now = [0.0]
    monkeypatch.setattr(summaries, "time", SimpleNamespace(monotonic=lambda: now[0]))

    def building(*_args: object, **_kwargs: object) -> str:
        now[0] += 10.0
        return ""

    class Waits(Fake):
        def summarize(self, request: SummaryRequest) -> SummaryReply | Unanswered:
            now[0] += 3.0
            return super().summarize(request)

    monkeypatch.setattr(call_summaries, "code_with_piece", building)
    run = Run([record(quartered(3))])

    turned(Waits(), run)

    assert run.paused == [3.0]


def test_an_entry_that_names_a_call_no_input_recorded_is_given_up_with_no_ask() -> None:
    lost = Source(SourceKind.LOST, "x", CALL, call="bin")
    notes: list[Note] = []
    tool = tool_of(fake := Fake(), notes, COUNTS)

    handled = taken(tool, Run([record()]), entry(lost))

    assert fake.requests == []
    assert handled == Handled((Outcome.GAVE_UP,), asked=False)
    assert notes == []


def test_an_entry_that_names_only_a_loop_is_given_up_with_no_ask() -> None:
    notes: list[Note] = []
    told = Told(scope=Scope.of_module(STUCK), tell=Tell(noted=notes.append))
    tool = Summaries(fake := Fake(), load_target(COUNTS), told, isolated=apart)
    lost = LossRun(
        CALL, "bin", LossKind.CALL, (GoingIn("arg1", "3", True),), (Changed("answer", '"0b11"'),)
    )
    waiting = InputRecord(args={}, forks=(), covered_lines=frozenset(), losses=(lost,))

    alone = tool.take((entry(LOOPED),), Moment(1, (), Run([])))
    tool.heard(waiting, 1)
    beside = tool.take((entry(LOOPED),), Moment(2, (), Run([waiting])))

    assert fake.requests == []
    assert alone == Handled((Outcome.GAVE_UP,), asked=False)
    assert beside == Handled((Outcome.SKIPPED,), asked=False)
    assert notes == []


def test_a_failed_ask_is_said_and_gives_the_entry_up() -> None:
    failed = Unanswered(Why.TIMED_OUT, "timed out after 30 s", AskCost(1))
    run = Run([record(quartered(3))])

    tool, notes = turned(Fake(failed), run)

    assert notes == [AskSkipped("summaries", "timed out after 30 s")]
    assert taken(tool, run, LOST) == Handled((Outcome.GAVE_UP,), asked=False)


def test_a_site_whose_ask_got_no_answer_is_listed_with_no_formula() -> None:
    failed = Unanswered(Why.TIMED_OUT, "timed out after 30 s", AskCost(2))

    tool, _ = turned(Fake(failed), Run([record(quartered(3))]))

    assert tool.states() == listed(None, SummaryState.UNANSWERED, 2)


def test_a_site_whose_reply_held_no_code_block_is_listed_as_failed() -> None:
    tool, _ = turned(Fake(), Run([record(quartered(3))]))

    assert tool.states() == listed(None, SummaryState.FAILED, 1)


def dropped(tool: Summaries, first: InputRecord) -> Run:
    """The run once its second input, which ran the site, dropped the site's formula in use."""
    drop = FormulaDrop(SITE, "answer", "1", "2", DropReason.MISMATCH, run=0)
    second = InputRecord(
        args={"n": 5},
        forks=(),
        covered_lines=frozenset(),
        losses=(quartered(5),),
        drops=(drop,),
    )
    tool.heard(second, 2)
    return Run([first, second])


def test_a_dropped_site_whose_next_ask_got_no_answer_is_listed_unanswered() -> None:
    first = record(quartered(3))
    tool, _ = turned(Fake(SummaryReply(QUARTER, AskCost(1))), Run([first]))
    run = dropped(tool, first)

    tool.provider = Fake(Unanswered(Why.TIMED_OUT, "timed out after 30 s", AskCost(2)))
    tool.between(run)

    assert tool.states() == listed(QUARTER, SummaryState.UNANSWERED, 2)


def test_a_listed_site_s_ask_the_token_limit_refused_leaves_its_state() -> None:
    first = record(quartered(3))
    tool, _ = turned(Fake(SummaryReply(QUARTER, AskCost(1))), Run([first]))
    run = dropped(tool, first)

    tool.provider = Fake(Unanswered(Why.LIMIT, "token limit reached", AskCost(2)))
    tool.between(run)

    assert tool.states() == listed(QUARTER, SummaryState.DROPPED, 1, 1)


def test_the_token_limit_ends_the_asks_unsaid() -> None:
    limit = Unanswered(Why.LIMIT, "token limit reached", AskCost(1))

    tool, notes = turned(fake := Fake(limit), Run([record(quartered(3), shift(36, 8, 3, 1))]))

    assert len(fake.requests) == 1
    assert notes == []
    assert not tool.can_ask


def test_a_site_whose_only_ask_met_the_token_limit_is_not_listed() -> None:
    limit = Unanswered(Why.LIMIT, "token limit reached", AskCost(1))

    tool, _ = turned(Fake(limit), Run([record(quartered(3))]))

    assert tool.states() == ()


def asked_call(runs: Sequence[AskedRun], parameters: tuple[str, ...]) -> AskedCall:
    """The site `SITE` as an ask sees it, with these complete runs, each of input 1."""
    complete = tuple(CompleteRun(1, each) for each in runs)
    return AskedCall(
        SITE,
        complete,
        parameters,
        (11, 11),
        "__pow__",
        LossKind.OPERATION,
        "pow(n, 1, 4)",
        None,
        1,
        ("n", None, None),
    )


def going(n: str, answer: str = "0") -> AskedRun:
    return AskedRun((GoingIn("n", n, True),), (Changed("answer", answer),))


def test_the_runs_shown_put_distinct_values_going_in_first_then_distinct_changed_values() -> None:
    # the last run's values going in are held back: its answer is its own
    runs = [going("1"), going("1"), going("1", "1"), going("2"), going("3", "7")]

    assert shown_runs(asked_call(runs, ("n",))) == (
        ShownRun((("n", "1"),), (("answer", "0"),)),
        ShownRun((("n", "2"),), (("answer", "0"),)),
        ShownRun((("n", "1"),), (("answer", "1"),)),
        ShownRun((("n", "1"),), (("answer", "0"),)),
    )


def test_the_runs_shown_are_ten_at_most() -> None:
    runs = [going(str(at)) for at in range(1, 13)]

    shown = shown_runs(asked_call(runs, ("n",)))

    assert [each.going_in[0][1] for each in shown] == [str(at) for at in range(1, 11)]


def test_a_checked_formula_takes_the_entry_and_is_kept_for_its_site() -> None:
    run = Run([record(quartered(3)), record(quartered(13))])

    tool, notes = turned(Fake(SummaryReply(QUARTER, AskCost(1))), run)

    assert notes == [
        SummaryRead(SITE, "answer = n % 4", call="__pow__"),
        SummaryChecked(SITE, 2, 1, call="__pow__"),
    ]
    in_use = SummaryState.IN_USE
    assert tool.sites[SITE] == SiteState(
        ("answer",), "__pow__", attempts=1, formula=QUARTER, checked_on=2, last=in_use
    )
    assert tool.states() == listed(QUARTER, in_use, 1, 2)
    assert taken(tool, run, LOST) == Handled((Outcome.TOOK,), asked=False)


def test_a_failed_try_gives_the_entry_up_and_is_kept_with_its_reason() -> None:
    run = Run([record(quartered(3))])

    tool, notes = turned(Fake(SummaryReply(WRONG, AskCost(3))), run)

    reason = "at input 1, answer was 3, the formula gave 9"
    assert notes[-1] == SummaryFailed(SITE, 3, reason, call="__pow__")
    assert tool.sites[SITE].tries == [EarlierFormula(WRONG, reason)]
    assert tool.sites[SITE].checked_on is None
    assert tool.states() == listed(WRONG, SummaryState.FAILED, 3)
    assert taken(tool, run, LOST) == Handled((Outcome.GAVE_UP,), asked=False)


def test_a_check_that_cannot_run_skips_the_site_at_its_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Thread(Fake):
        def summarize(self, request: SummaryRequest) -> SummaryReply | Unanswered:
            monkeypatch.setattr(model_runs, "running", lambda: 2)
            return super().summarize(request)

    tool, notes = turned(Thread(SummaryReply(QUARTER, AskCost(1))), Run([record(quartered(3))]))

    assert notes[-1] == SummarySkipped(SITE, "cannot fork", call="__pow__")
    assert tool.states() == listed(QUARTER, SummaryState.UNCHECKED, 1)


def test_a_check_the_run_s_deadline_ends_skips_the_site_and_keeps_no_failed_try() -> None:
    slow = 'def summary(n):\n    return {"answer": math.factorial(10 ** 7)}\n'
    run = Run([record(quartered(3))], bounds=Bounds(until=time.monotonic() + 0.3))

    tool, notes = turned(Fake(SummaryReply(slow, AskCost(1))), run)

    assert notes[-1] == SummarySkipped(SITE, "the run's budget ran out", call="__pow__")
    assert tool.sites[SITE].tries == []
    assert tool.states() == listed(slow, SummaryState.UNCHECKED, 1)


# llm-stuck-moment-needs-a-tool-that-can-ask-token-limit
@pytest.mark.parametrize(
    ("answer", "can_ask"),
    [
        (SummaryReply(QUARTER, AskCost(1, tokens_left=5)), True),
        (SummaryReply(QUARTER, AskCost(1, tokens_left=0)), False),
        (SummaryReply(QUARTER, AskCost(1)), True),
        (Unanswered(Why.PROVIDER, "provider error 500", AskCost(1, tokens_left=5)), True),
        (Unanswered(Why.LIMIT, "token limit reached", AskCost(1)), False),
    ],
    ids=["tokens left", "none left", "left unknown", "failed ask", "limit"],
)
def test_summaries_can_ask_until_an_answer_leaves_no_token(
    answer: SummaryReply | Unanswered, can_ask: bool
) -> None:
    notes: list[Note] = []
    tool = tool_of(Fake(answer), notes)
    assert tool.can_ask is True
    run = Run([record(quartered(3))])
    tool.heard(run.records[0], 1)

    tool.between(run)

    assert tool.can_ask is can_ask

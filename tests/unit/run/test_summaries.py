"""The summaries tool at a stuck moment: which loops it asks about, with which runs, and what it
hands back for each entry, given records made by hand."""

import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from pyct.binding.bind import Seed
from pyct.branches.plan import Plan
from pyct.core.foundation.branch import Changed, GoingIn, PieceRun, Site
from pyct.results.causes import Condition, Reason, Source, SourceKind, WhyEntry
from pyct.results.coverage import Scope
from pyct.results.llm_asks import AskCost, LoopSummary, Unanswered, Why
from pyct.results.record import InputRecord, Stop, StopKind
from pyct.results.record import Source as RecordSource
from pyct.run import model_runs, summaries
from pyct.run.bounds import Bounds
from pyct.run.notes import (
    AskSkipped,
    Note,
    SummaryChecked,
    SummaryFailed,
    SummaryRead,
    SummarySkipped,
)
from pyct.run.stuck import Handled, Moment, Outcome
from pyct.run.summaries import (
    AskedLoop,
    EarlierFormula,
    LoopState,
    ShownRun,
    Summaries,
    SummaryReply,
    SummaryRequest,
    asked_loop,
    piece_at,
    shown_runs,
)
from pyct.run.summary_checks import CompleteRun
from pyct.run.target import load_target
from pyct.run.tell import Ask, Tell, Told
from tests.acceptance.harness import REPO_ROOT

FILE = str(REPO_ROOT / "targets" / "why" / "stuck.py")
LOOP = Site(FILE, 10, 4)
COMPREHENSION = Site(FILE, 19, 11)
CALL = Site(FILE, 26, 7)
COUNTS = "targets.why.stuck::counts"


def counted(s: str, *, tracked: bool = True, changed: bool = True) -> PieceRun:
    """A run of ``counts``'s loop on ``s``."""
    going_in = (GoingIn("s", f'"{s}"', tracked), GoingIn("t", "0", False))
    return PieceRun(LOOP, going_in, (Changed("t", str(s.count("z"))),) if changed else ())


def record(*runs: PieceRun) -> InputRecord:
    return InputRecord(args={}, forks=(), covered_lines=frozenset(), pieces=runs)


def entry(*sources: Source, line: int = 14) -> WhyEntry:
    condition = Condition(Site(FILE, line - 1, 7), True)
    return WhyEntry(FILE, (line,), Reason.NO_FORK, condition=condition, sources=sources)


LOOPED = Source(SourceKind.LOOP, "t", LOOP)


@dataclass
class Run:
    """The run as a moment sees it, its records made by hand."""

    records: Sequence[InputRecord]
    bounds: Bounds = field(default_factory=Bounds)
    stopped: Stop | None = None
    paused: list[float] = field(default_factory=list)

    def causes(self, stop_at: float | None) -> tuple[WhyEntry, ...]:
        return ()

    def run_input(
        self, seed: Seed, source: RecordSource, wanted: Plan | None = None
    ) -> InputRecord | Stop:
        raise AssertionError("summaries run no input")

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


def taken(
    fake: Fake, entries: Sequence[WhyEntry], records: Sequence[InputRecord]
) -> tuple[Handled, list[Note], Run]:
    notes: list[Note] = []
    told = Told(scope=Scope.of_module(FILE), tell=Tell(noted=notes.append))
    tool = Summaries(fake, load_target("targets.why.stuck::counts"), told)
    run = Run(records)
    return tool.take(tuple(entries), Moment(1, tuple(entries), run)), notes, run


def test_the_clock_pauses_for_the_model_s_wait_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    now = [0.0]
    monkeypatch.setattr(summaries, "time", SimpleNamespace(monotonic=lambda: now[0]))

    def building(*_args: object) -> str:
        now[0] += 10.0
        return ""

    class Waits(Fake):
        def summarize(self, request: SummaryRequest) -> SummaryReply | Unanswered:
            now[0] += 3.0
            return super().summarize(request)

    monkeypatch.setattr(summaries, "code_with_piece", building)

    _, _, run = taken(Waits(), [entry(LOOPED)], [record(counted("a"))])

    assert run.paused == [3.0]


def test_a_loop_two_entries_name_is_asked_about_once() -> None:
    fake = Fake()

    handled, _, run = taken(fake, [entry(LOOPED), entry(LOOPED, line=15)], [record(counted("a"))])

    assert len(fake.requests) == 1
    assert handled == Handled((Outcome.GAVE_UP, Outcome.GAVE_UP), asked=True)
    assert len(run.paused) == 1


def test_an_entry_that_names_a_call_is_given_up_and_no_call_is_asked_about() -> None:
    lost = Source(SourceKind.LOST, "x", CALL, call="bin")

    handled, notes, _ = taken(fake := Fake(), [entry(lost)], [record(counted("a"))])

    assert fake.requests == []
    assert handled == Handled((Outcome.GAVE_UP,), asked=False)
    assert notes == []


def test_a_loop_with_no_complete_run_is_skipped_and_said() -> None:
    records = [record(counted("a", changed=False)), record()]

    handled, notes, _ = taken(fake := Fake(), [entry(LOOPED)], records)

    assert fake.requests == []
    assert handled == Handled((Outcome.SKIPPED,), asked=False)
    assert notes == [SummarySkipped(LOOP, "no recorded run")]


def test_a_failed_ask_is_said_and_skips_the_entry() -> None:
    failed = Unanswered(Why.TIMED_OUT, "timed out after 30 s", AskCost(1))

    handled, notes, _ = taken(Fake(failed), [entry(LOOPED)], [record(counted("a"))])

    assert handled == Handled((Outcome.SKIPPED,), asked=True)
    assert notes == [AskSkipped("summaries", "timed out after 30 s")]


def test_a_loop_whose_ask_got_no_answer_is_listed_with_no_formula() -> None:
    notes: list[Note] = []
    told = Told(scope=Scope.of_module(FILE), tell=Tell(noted=notes.append))
    failed = Unanswered(Why.TIMED_OUT, "timed out after 30 s", AskCost(2))
    tool = Summaries(Fake(failed), load_target(COUNTS), told)

    tool.take((entry(LOOPED),), Moment(1, (), Run([record(counted("a"))])))

    assert tool.states() == (LoopSummary(FILE, 10, 4, ("t",), None, 2),)


def test_the_token_limit_ends_the_asks_unsaid() -> None:
    limit = Unanswered(Why.LIMIT, "token limit reached", AskCost(1))
    second = Source(SourceKind.LOOP, "t", COMPREHENSION)
    comprehended = PieceRun(COMPREHENSION, (GoingIn("s", '"a"', True),), (Changed("t", "0"),))

    handled, notes, _ = taken(
        fake := Fake(limit), [entry(LOOPED), entry(second)], [record(counted("a"), comprehended)]
    )

    assert len(fake.requests) == 1
    assert handled == Handled((Outcome.SKIPPED, Outcome.SKIPPED), asked=True)
    assert notes == []


def test_a_loop_whose_only_ask_met_the_token_limit_is_not_listed() -> None:
    told = Told(scope=Scope.of_module(FILE), tell=Tell())
    limit = Unanswered(Why.LIMIT, "token limit reached", AskCost(1))
    tool = Summaries(Fake(limit), load_target(COUNTS), told)

    tool.take((entry(LOOPED),), Moment(1, (), Run([record(counted("a"))])))

    assert tool.states() == ()


def test_no_ask_is_made_once_the_run_has_stopped() -> None:
    notes: list[Note] = []
    told = Told(scope=Scope.of_module(FILE), tell=Tell(noted=notes.append))
    tool = Summaries(fake := Fake(), load_target("targets.why.stuck::counts"), told)
    run = Run([record(counted("a"))], stopped=Stop(StopKind.BUDGET))

    handled = tool.take((entry(LOOPED),), Moment(1, (), run))

    assert (fake.requests, handled.outcomes) == ([], (Outcome.SKIPPED,))


def test_a_loop_s_complete_runs_and_parameters_come_from_every_record() -> None:
    plain = PieceRun(LOOP, (GoingIn("s", '"q"', True),), (Changed("t", "0"),))
    records = [record(counted("a"), counted("z")), record(), record(plain)]

    loop = asked_loop(LOOP, records)

    assert loop is not None
    assert [each.number for each in loop.runs] == [1, 1, 3]
    # t was unbound going into the last run, so it is no parameter
    assert loop.parameters == ("s",)


def test_the_runs_shown_put_distinct_values_going_in_first_then_distinct_changed_values() -> None:
    piece = piece_at(LOOP)
    assert piece is not None

    def going(s: str, t: str = "0") -> PieceRun:
        return PieceRun(LOOP, (GoingIn("s", s, True),), (Changed("t", t),))

    runs = [going('"a"'), going('"a"'), going('"a"', "1"), going('"b"')]
    loop = AskedLoop(LOOP, piece, tuple(CompleteRun(1, each) for each in runs), ("s",))

    assert shown_runs(loop) == (
        ShownRun((("s", '"a"'),), (("t", "0"),)),
        ShownRun((("s", '"b"'),), (("t", "0"),)),
        ShownRun((("s", '"a"'),), (("t", "1"),)),
        ShownRun((("s", '"a"'),), (("t", "0"),)),
    )


def test_the_runs_shown_are_ten_at_most() -> None:
    piece = piece_at(LOOP)
    assert piece is not None
    runs = tuple(CompleteRun(at, counted(str(at))) for at in range(1, 13))

    shown = shown_runs(AskedLoop(LOOP, piece, runs, ("s", "t")))

    assert [each.going_in[0][1] for each in shown] == [f'"{at}"' for at in range(1, 11)]


def test_the_piece_at_a_site_is_read_off_its_file() -> None:
    piece = piece_at(COMPREHENSION)

    assert piece is not None
    assert (piece.going_in, piece.changed, piece.lines) == (("s",), ("t",), (19, 19))
    assert piece_at(Site(FILE, 13, 4)) is None
    assert piece_at(Site("/nowhere/gone.py", 1, 0)) is None


FORMULA = 'def summary(s, t):\n    return {"t": t + s.count("z")}\n'


def test_a_checked_formula_takes_the_entry_and_is_kept_for_its_loop() -> None:
    notes: list[Note] = []
    told = Told(scope=Scope.of_module(FILE), tell=Tell(noted=notes.append))
    fake = Fake(SummaryReply(FORMULA, AskCost(1)))
    tool = Summaries(fake, load_target("targets.why.stuck::counts"), told)
    run = Run([record(counted("ab")), record(counted("zz"))])

    handled = tool.take((entry(LOOPED),), Moment(1, (), run))

    assert handled == Handled((Outcome.TOOK,), asked=True)
    assert notes == [
        SummaryRead(LOOP, 't = t + s.count("z")'),
        SummaryChecked(LOOP, 2),
    ]
    assert tool.loops[LOOP] == LoopState(("t",), attempts=1, formula=FORMULA, checked_on=2)
    assert tool.states() == (LoopSummary(FILE, 10, 4, ("t",), FORMULA, 1, 2),)


def test_a_failed_try_gives_the_entry_up_and_is_kept_with_its_reason() -> None:
    notes: list[Note] = []
    told = Told(scope=Scope.of_module(FILE), tell=Tell(noted=notes.append))
    wrong = 'def summary(s, t):\n    return {"t": len(s)}\n'
    tool = Summaries(Fake(SummaryReply(wrong, AskCost(3))), load_target(COUNTS), told)

    handled = tool.take((entry(LOOPED),), Moment(1, (), Run([record(counted("ab"))])))

    reason = "at input 1, t was 0, the formula gave 2"
    assert handled == Handled((Outcome.GAVE_UP,), asked=True)
    assert notes[-1] == SummaryFailed(LOOP, 3, reason)
    assert tool.loops[LOOP].tries == [EarlierFormula(wrong, reason)]
    assert tool.loops[LOOP].checked_on is None
    assert tool.states() == (LoopSummary(FILE, 10, 4, ("t",), wrong, 3),)


def test_a_check_that_cannot_run_skips_the_loop_at_this_moment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notes: list[Note] = []
    told = Told(scope=Scope.of_module(FILE), tell=Tell(noted=notes.append))
    tool = Summaries(Fake(SummaryReply(FORMULA, AskCost(1))), load_target(COUNTS), told)

    class Thread(Fake):
        def summarize(self, request: SummaryRequest) -> SummaryReply | Unanswered:
            monkeypatch.setattr(model_runs, "running", lambda: 2)
            return super().summarize(request)

    tool.provider = Thread(SummaryReply(FORMULA, AskCost(1)))
    handled = tool.take((entry(LOOPED),), Moment(1, (), Run([record(counted("ab"))])))

    assert handled == Handled((Outcome.SKIPPED,), asked=True)
    assert notes[-1] == SummarySkipped(LOOP, "cannot fork")


def test_a_check_the_run_s_deadline_ends_skips_the_loop_and_keeps_no_failed_try() -> None:
    notes: list[Note] = []
    told = Told(scope=Scope.of_module(FILE), tell=Tell(noted=notes.append))
    slow = 'def summary(s, t):\n    return {"t": math.factorial(10 ** 7)}\n'
    tool = Summaries(Fake(SummaryReply(slow, AskCost(1))), load_target(COUNTS), told)
    run = Run([record(counted("ab"))], bounds=Bounds(until=time.monotonic() + 0.3))

    handled = tool.take((entry(LOOPED),), Moment(1, (), run))

    assert handled == Handled((Outcome.SKIPPED,), asked=True)
    assert notes[-1] == SummarySkipped(LOOP, "the run's budget ran out")
    assert tool.loops[LOOP].tries == []


# llm-stuck-moment-needs-a-tool-that-can-ask-token-limit
@pytest.mark.parametrize(
    ("answer", "can_ask"),
    [
        (SummaryReply(FORMULA, AskCost(1, tokens_left=5)), True),
        (SummaryReply(FORMULA, AskCost(1, tokens_left=0)), False),
        (SummaryReply(FORMULA, AskCost(1)), True),
        (Unanswered(Why.PROVIDER, "provider error 500", AskCost(1, tokens_left=5)), True),
        (Unanswered(Why.LIMIT, "token limit reached", AskCost(1)), False),
    ],
    ids=["tokens left", "none left", "left unknown", "failed ask", "limit"],
)
def test_summaries_can_ask_until_an_answer_leaves_no_token(
    answer: SummaryReply | Unanswered, can_ask: bool
) -> None:
    tool = Summaries(
        Fake(answer), load_target(COUNTS), Told(scope=Scope.of_module(FILE), tell=Tell())
    )
    assert tool.can_ask is True

    tool.take((entry(LOOPED),), Moment(1, (), Run([record(counted("ab"))])))

    assert tool.can_ask is can_ask

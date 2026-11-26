"""The stuck moment hands each LLM tool its entries, in the order summaries, rewrites, guesses,
by each entry's cause, and passes what a tool gave up on to guesses."""

import dataclasses
import time
from collections.abc import Sequence
from dataclasses import dataclass, field

import pytest

from pyct.binding.bind import Seed
from pyct.config.goal import Goal
from pyct.core.foundation.branch import Site
from pyct.results.causes import Condition, Reason, Source, SourceKind, Tries, WhyEntry
from pyct.results.coverage import Progress, Reach, Scope
from pyct.results.graphs import LONGEST_STRETCH
from pyct.results.record import InputRecord, Stop, StopKind
from pyct.run.bounds import Bounds
from pyct.run.stuck import CAUSE_SECONDS, Handled, Kind, Moment, Outcome, Stuck, owner

FILE = "m.py"


def site(line: int) -> Site:
    return Site(file=FILE, line=line, col=7)


# one entry of each cause a tool takes, and two no tool takes
LOOPED = WhyEntry(
    FILE,
    (4,),
    Reason.NO_FORK,
    condition=Condition(site(3), True),
    sources=(Source(SourceKind.LOOP, "t", site(2)),),
)
TIMED_OUT = WhyEntry(
    FILE, (6,), Reason.NOT_TAKEN, condition=Condition(site(5), True), tries=Tries(timeout=1)
)
NO_SOURCE = WhyEntry(FILE, (8,), Reason.NO_FORK, condition=Condition(site(7), True), sources=())
HANDLER = WhyEntry(FILE, (10,), Reason.HANDLER)
ENDED = WhyEntry(FILE, (12,), Reason.ENDED_BEFORE)
UNSAT = WhyEntry(
    FILE, (14,), Reason.NOT_TAKEN, condition=Condition(site(13), True), tries=Tries(unsat=2)
)
NOT_CALLED = WhyEntry(FILE, (16,), Reason.NOT_CALLED, function="g")
CUT_SHORT = WhyEntry(FILE, (18,), Reason.NOT_WORKED_OUT)
LOST = WhyEntry(
    FILE,
    (20,),
    Reason.NO_FORK,
    condition=Condition(site(19), True),
    sources=(Source(SourceKind.LOST, "k", site(18), call="__pow__"),),
)
# a lost source beside a loop source
LOST_AND_LOOPED = dataclasses.replace(
    LOST, sources=(*(LOST.sources or ()), Source(SourceKind.LOOP, "t", site(17)))
)
EVERY = (LOOPED, TIMED_OUT, NO_SOURCE, HANDLER, ENDED, UNSAT, NOT_CALLED, CUT_SHORT, LOST)


@dataclass
class FakeRun:
    """A run part way through, whose causes are fixed and whose inputs a tool can add to."""

    causes_given: tuple[WhyEntry, ...] = EVERY
    bounds: Bounds = field(default_factory=Bounds)
    records: list[InputRecord] = field(default_factory=list)
    stopped: Stop | None = None
    stops: list[float | None] = field(default_factory=list)

    def causes(self, stop_at: float | None) -> tuple[WhyEntry, ...]:
        self.stops.append(stop_at)
        return self.causes_given

    def run_input(self, seed: Seed, source: object, wanted: object = None) -> InputRecord | Stop:
        raise AssertionError("no fake tool here runs an input")

    def tell_ask(self, ask: object) -> None:
        pass

    def pause(self, seconds: float) -> None:
        self.bounds = self.bounds.paused(seconds)


@dataclass
class FakeTool:
    """A tool that answers each entry with the outcome it is given for it, and notes what it was
    handed at each moment."""

    kind: Kind
    outcomes: dict[WhyEntry, Outcome] = field(default_factory=dict)
    asks: bool = True
    can_ask: bool = True
    handed: list[tuple[int, tuple[WhyEntry, ...]]] = field(default_factory=list)
    order: list[Kind] | None = None
    waits: bool = False

    def take(self, entries: tuple[WhyEntry, ...], moment: Moment) -> Handled:
        self.handed.append((moment.number, entries))
        if self.order is not None:
            self.order.append(self.kind)
        outcomes = tuple(self.outcomes.get(entry, Outcome.SKIPPED) for entry in entries)
        return Handled(outcomes, asked=self.asks)

    def heard(self, record: InputRecord, number: int) -> None:
        pass

    def waiting(self, moment: Moment) -> bool:
        return self.waits


def held(tools: Sequence[FakeTool], run: FakeRun | None = None) -> FakeRun:
    run = run or FakeRun()
    Stuck(tools).hold(run)
    return run


def due(tools: Sequence[FakeTool]) -> bool:
    """Whether a moment comes for a run with a line missed and no fork left to flip."""
    return Stuck(tools).due(
        FakeRun(), Progress(Scope(FILE, frozenset({4})), frozenset()), empty=True
    )


# llm-stuck-moment-needs-a-tool-that-can-ask-token-limit
def test_no_moment_comes_when_no_tool_can_still_ask() -> None:
    assert due([FakeTool(Kind.SUMMARIES, can_ask=False)]) is False


def test_a_moment_comes_while_one_tool_can_still_ask() -> None:
    tools = [FakeTool(Kind.SUMMARIES, can_ask=False), FakeTool(Kind.REWRITES)]

    assert due(tools) is True


def test_no_moment_comes_with_no_tool() -> None:
    assert due([]) is False


def test_each_tool_takes_the_entries_of_its_causes() -> None:
    summaries, rewrites, guesses = (FakeTool(kind) for kind in Kind)

    held([guesses, rewrites, summaries])

    assert summaries.handed == [(1, (LOST,))]
    assert rewrites.handed == [(1, (LOOPED, TIMED_OUT, NO_SOURCE, UNSAT))]
    assert guesses.handed == [(1, (HANDLER, ENDED))]


def test_the_tools_take_their_turns_in_the_order_summaries_rewrites_guesses() -> None:
    order: list[Kind] = []
    tools = [FakeTool(kind, order=order) for kind in (Kind.GUESSES, Kind.SUMMARIES, Kind.REWRITES)]

    held(tools)

    assert order == [Kind.SUMMARIES, Kind.REWRITES, Kind.GUESSES]


def test_guesses_take_a_switched_off_tool_s_entries_in_line_order() -> None:
    guesses = FakeTool(Kind.GUESSES)

    held([guesses])

    assert guesses.handed == [(1, (LOOPED, TIMED_OUT, NO_SOURCE, HANDLER, ENDED, UNSAT, LOST))]


def test_guesses_take_what_a_tool_gave_up_on_and_not_what_it_took() -> None:
    summaries = FakeTool(Kind.SUMMARIES, {LOST: Outcome.GAVE_UP})
    rewrites = FakeTool(Kind.REWRITES, {LOOPED: Outcome.GAVE_UP, TIMED_OUT: Outcome.TOOK})
    guesses = FakeTool(Kind.GUESSES)

    held([summaries, rewrites, guesses])

    assert guesses.handed == [(1, (LOOPED, HANDLER, ENDED, LOST))]


# llm-rewrite-no-fork-no-source-goes-to-guesses-after-rewrites
def test_guesses_take_an_entry_with_no_source_at_the_moment_rewrites_give_it_up() -> None:
    rewrites = FakeTool(Kind.REWRITES, {NO_SOURCE: Outcome.GAVE_UP})
    guesses = FakeTool(Kind.GUESSES)

    held([rewrites, guesses], FakeRun(causes_given=(NO_SOURCE,)))

    assert rewrites.handed == [(1, (NO_SOURCE,))]
    assert guesses.handed == [(1, (NO_SOURCE,))]


def test_guesses_take_what_a_tool_gave_up_on_at_an_earlier_moment() -> None:
    summaries = FakeTool(Kind.SUMMARIES, {LOST: Outcome.GAVE_UP})
    guesses = FakeTool(Kind.GUESSES)
    stuck = Stuck([summaries, guesses])
    stuck.hold(FakeRun(causes_given=(LOST,)))
    # at the second moment the summary's ask is skipped
    summaries.outcomes = {}

    stuck.hold(FakeRun(causes_given=(LOST,)))

    assert guesses.handed == [(1, (LOST,)), (2, (LOST,))]


def test_guesses_leave_an_entry_given_up_earlier_that_its_tool_takes_now() -> None:
    summaries = FakeTool(Kind.SUMMARIES, {LOST: Outcome.GAVE_UP})
    guesses = FakeTool(Kind.GUESSES)
    stuck = Stuck([summaries, guesses])
    stuck.hold(FakeRun(causes_given=(LOST,)))
    summaries.outcomes = {LOST: Outcome.TOOK}

    stuck.hold(FakeRun(causes_given=(LOST,)))

    assert guesses.handed == [(1, (LOST,))]


def test_a_tool_with_no_entry_is_not_handed_any() -> None:
    rewrites = FakeTool(Kind.REWRITES)

    held([rewrites], FakeRun(causes_given=(HANDLER, NOT_CALLED)))

    assert rewrites.handed == []


def test_a_tool_answers_every_entry_it_was_handed() -> None:
    @dataclass
    class Short(FakeTool):
        def take(self, entries: tuple[WhyEntry, ...], moment: Moment) -> Handled:
            return Handled((), asked=True)

    with pytest.raises(ValueError):
        held([Short(Kind.GUESSES)])


def test_the_causes_stop_two_seconds_after_the_moment_starts() -> None:
    before = time.monotonic()

    run = held([FakeTool(Kind.GUESSES)])

    (stop_at,) = run.stops
    assert stop_at is not None
    assert before + CAUSE_SECONDS - LONGEST_STRETCH <= stop_at
    assert stop_at <= time.monotonic() + CAUSE_SECONDS - LONGEST_STRETCH


def test_the_causes_stop_at_the_deadline_when_it_comes_first() -> None:
    until = time.monotonic() + 0.5

    run = held([FakeTool(Kind.GUESSES)], FakeRun(bounds=Bounds(until=until)))

    assert run.stops == [until - LONGEST_STRETCH]


def test_a_stop_a_tool_meets_ends_the_moment() -> None:
    @dataclass
    class Stopping(FakeTool):
        def take(self, entries: tuple[WhyEntry, ...], moment: Moment) -> Handled:
            assert isinstance(moment.run, FakeRun)
            moment.run.stopped = Stop(kind=StopKind.BUDGET)
            return super().take(entries, moment)

    guesses = FakeTool(Kind.GUESSES)

    held([Stopping(Kind.SUMMARIES), guesses])

    assert guesses.handed == []


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        (LOOPED, Kind.REWRITES),
        (TIMED_OUT, Kind.REWRITES),
        (NO_SOURCE, Kind.REWRITES),
        (LOST, Kind.SUMMARIES),
        (LOST_AND_LOOPED, Kind.SUMMARIES),
        (HANDLER, Kind.GUESSES),
        (ENDED, Kind.GUESSES),
        (UNSAT, Kind.REWRITES),
        (dataclasses.replace(UNSAT, tries=Tries(unsat=1, unknown=1)), Kind.REWRITES),
        (dataclasses.replace(UNSAT, tries=Tries(left_the_plan=1, decided=1, not_tried=1)), None),
        (NOT_CALLED, None),
        (CUT_SHORT, None),
    ],
)
def test_an_entry_s_cause_names_the_tool_that_takes_it_first(
    entry: WhyEntry, expected: Kind | None
) -> None:
    assert owner(entry) is expected


def test_a_waiting_tool_with_no_entry_is_handed_the_moment() -> None:
    summaries, rewrites = FakeTool(Kind.SUMMARIES, waits=True), FakeTool(Kind.REWRITES)

    held([summaries, rewrites], FakeRun(causes_given=(HANDLER,)))

    assert summaries.handed == [(1, ())]
    assert rewrites.handed == []


@pytest.mark.parametrize(("asks", "left"), [(True, False), (False, True)])
def test_a_waiting_tool_s_moment_counts_toward_three_only_when_it_asks(
    asks: bool, left: bool
) -> None:
    stuck = Stuck([FakeTool(Kind.SUMMARIES, asks=asks, waits=True)])
    run = FakeRun(causes_given=(HANDLER,))
    progress = Progress(Scope(FILE, frozenset({4})), frozenset())

    for _ in range(3):
        stuck.hold(run)
        run.records.append(InputRecord(args={}, forks=(), covered_lines=frozenset()))

    assert stuck.due(run, progress, empty=True) is left


def test_no_moment_comes_for_a_waiting_tool_that_can_no_longer_ask() -> None:
    assert due([FakeTool(Kind.SUMMARIES, can_ask=False, waits=True)]) is False


@dataclass
class Turns:
    """A tool that asks between passes, and counts its turns, and keeps what it was called on in
    order."""

    can_ask: bool = True
    turns: int = 0
    calls: list[tuple[str, object]] = field(default_factory=list)

    def between(self, run: object) -> None:
        self.turns += 1
        self.calls.append(("between", run))

    def run_again(self, run: object) -> None:
        self.calls.append(("run again", run))


# the bounds of a run whose goal is bugs, which goes on past full coverage
BUGS = Bounds(goal=Goal.BUGS)


def missing(*lines: int) -> Progress:
    """The progress of a run of `FILE`'s lines 4 and 5 whose one input covered the others."""
    progress = Progress(Scope(FILE, frozenset({4, 5})), frozenset())
    progress.add(frozenset({4, 5}) - set(lines), Reach())
    return progress


@pytest.mark.parametrize(
    ("run", "progress", "turns"),
    [
        pytest.param(FakeRun(), missing(5), 1, id="a line missed"),
        pytest.param(FakeRun(), missing(), 0, id="every line covered"),
        pytest.param(FakeRun(stopped=Stop(kind=StopKind.BUDGET)), missing(5), 0, id="a stop met"),
        pytest.param(FakeRun(bounds=Bounds(until=0.0)), missing(5), 0, id="the budget spent"),
        pytest.param(FakeRun(bounds=BUGS), missing(), 1, id="every line covered, goal bugs"),
        pytest.param(
            FakeRun(bounds=BUGS, stopped=Stop(kind=StopKind.BUDGET)),
            missing(),
            0,
            id="a stop met, goal bugs",
        ),
        pytest.param(
            FakeRun(bounds=Bounds(until=0.0, goal=Goal.BUGS)),
            missing(),
            0,
            id="the budget spent, goal bugs",
        ),
    ],
)
def test_the_turn_between_passes_comes_while_the_run_goes_on_for_its_goal(
    run: FakeRun, progress: Progress, turns: int
) -> None:
    tool = Turns()

    Stuck([], between=tool).between(run, progress)

    assert tool.turns == turns


def test_the_inputs_a_turn_used_run_again_after_it() -> None:
    tool = Turns()
    run = FakeRun()

    Stuck([], between=tool).between(run, missing(5))

    assert tool.calls == [("between", run), ("run again", run)]

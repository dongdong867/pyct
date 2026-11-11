"""The stuck moment hands each LLM tool its entries, in the order summaries, rewrites, guesses,
by each entry's cause, and passes what a tool gave up on to guesses."""

import dataclasses
import time
from collections.abc import Sequence
from dataclasses import dataclass, field

import pytest

from pyct.binding.bind import Seed
from pyct.core.foundation.branch import Site
from pyct.results.causes import Condition, Reason, Source, SourceKind, Tries, WhyEntry
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
EVERY = (LOOPED, TIMED_OUT, NO_SOURCE, HANDLER, ENDED, UNSAT, NOT_CALLED, CUT_SHORT)


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

    def run_input(self, seed: Seed, source: object) -> InputRecord | Stop:
        raise AssertionError("no fake tool here runs an input")

    def pause(self, seconds: float) -> None:
        self.bounds = self.bounds.paused(seconds)


@dataclass
class FakeTool:
    """A tool that answers each entry with the outcome it is given for it, and notes what it was
    handed at each moment."""

    kind: Kind
    outcomes: dict[WhyEntry, Outcome] = field(default_factory=dict)
    asks: bool = True
    handed: list[tuple[int, tuple[WhyEntry, ...]]] = field(default_factory=list)
    order: list[Kind] | None = None

    def take(self, entries: tuple[WhyEntry, ...], moment: Moment) -> Handled:
        self.handed.append((moment.number, entries))
        if self.order is not None:
            self.order.append(self.kind)
        outcomes = tuple(self.outcomes.get(entry, Outcome.SKIPPED) for entry in entries)
        return Handled(outcomes, asked=self.asks)


def held(tools: Sequence[FakeTool], run: FakeRun | None = None) -> FakeRun:
    run = run or FakeRun()
    Stuck(tools).hold(run)
    return run


def test_each_tool_takes_the_entries_of_its_causes() -> None:
    summaries, rewrites, guesses = (FakeTool(kind) for kind in Kind)

    held([guesses, rewrites, summaries])

    assert summaries.handed == [(1, (LOOPED,))]
    assert rewrites.handed == [(1, (TIMED_OUT,))]
    assert guesses.handed == [(1, (NO_SOURCE, HANDLER, ENDED))]


def test_the_tools_take_their_turns_in_the_order_summaries_rewrites_guesses() -> None:
    order: list[Kind] = []
    tools = [FakeTool(kind, order=order) for kind in (Kind.GUESSES, Kind.SUMMARIES, Kind.REWRITES)]

    held(tools)

    assert order == [Kind.SUMMARIES, Kind.REWRITES, Kind.GUESSES]


def test_guesses_take_a_switched_off_tool_s_entries_in_line_order() -> None:
    guesses = FakeTool(Kind.GUESSES)

    held([guesses])

    assert guesses.handed == [(1, (LOOPED, TIMED_OUT, NO_SOURCE, HANDLER, ENDED))]


def test_guesses_take_what_a_tool_gave_up_on_and_not_what_it_took() -> None:
    summaries = FakeTool(Kind.SUMMARIES, {LOOPED: Outcome.GAVE_UP})
    rewrites = FakeTool(Kind.REWRITES, {TIMED_OUT: Outcome.TOOK})
    guesses = FakeTool(Kind.GUESSES)

    held([summaries, rewrites, guesses])

    assert guesses.handed == [(1, (LOOPED, NO_SOURCE, HANDLER, ENDED))]


def test_guesses_take_what_a_tool_gave_up_on_at_an_earlier_moment() -> None:
    summaries = FakeTool(Kind.SUMMARIES, {LOOPED: Outcome.GAVE_UP})
    guesses = FakeTool(Kind.GUESSES)
    stuck = Stuck([summaries, guesses])
    stuck.hold(FakeRun(causes_given=(LOOPED,)))
    # at the second moment the summary's ask is skipped
    summaries.outcomes = {}

    stuck.hold(FakeRun(causes_given=(LOOPED,)))

    assert guesses.handed == [(1, (LOOPED,)), (2, (LOOPED,))]


def test_a_tool_with_no_entry_is_not_handed_any() -> None:
    rewrites = FakeTool(Kind.REWRITES)

    held([rewrites], FakeRun(causes_given=(LOOPED, UNSAT)))

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
        (LOOPED, Kind.SUMMARIES),
        (TIMED_OUT, Kind.REWRITES),
        (NO_SOURCE, Kind.GUESSES),
        (HANDLER, Kind.GUESSES),
        (ENDED, Kind.GUESSES),
        (UNSAT, None),
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

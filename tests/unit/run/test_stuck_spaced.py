"""After a stuck moment in which no tool asked, the wait before the next one doubles, on both
rules, and goes back when a tool asks or an input covers a new line; each test adds its inputs
one by one and moves a clock of its own."""

from collections.abc import Collection, Sequence
from dataclasses import dataclass

from pyct.results.causes import WhyEntry
from pyct.results.coverage import Progress, Scope
from pyct.results.record import InputRecord
from pyct.run.bounds import Bounds
from pyct.run.stuck import Handled, Kind, Moment, Outcome, Stuck
from tests.unit.run.test_stuck_time import FILE, Clock, FakeRun

BUDGET = 40.0
# line 99 stays missed; each new line an input covers is one of the others
LINES = frozenset(range(1, 100))


@dataclass
class Asking:
    """A tool that asks at the n-th moment as the n-th of ``asks`` says, and the last says for
    each later moment; at its first moment it runs an input that covers ``covers``, if given."""

    asks: Sequence[bool]
    covers: int | None = None
    kind: Kind = Kind.GUESSES
    can_ask: bool = True
    moments: int = 0

    def take(self, entries: tuple[WhyEntry, ...], moment: Moment) -> Handled:
        asked = self.asks[min(self.moments, len(self.asks) - 1)]
        if self.moments == 0 and self.covers is not None:
            assert isinstance(moment.run, FakeRun)
            moment.run.add(self.covers)
        self.moments += 1
        return Handled(tuple(Outcome.SKIPPED for _ in entries), asked=asked)

    def heard(self, record: InputRecord, number: int) -> None:
        pass

    def waiting(self, moment: Moment) -> bool:
        return False


def seeded(
    asks: Sequence[bool], bounds: Bounds | None = None, covers: int | None = None
) -> tuple[Clock, FakeRun, Stuck]:
    """A run whose one seed covered line 1, first looked at as its seed ended, at 0."""
    clock = Clock()
    run = FakeRun(bounds=bounds or Bounds(), progress=Progress(Scope(FILE, LINES), frozenset()))
    run.add(1)
    stuck = Stuck([Asking(asks, covers)], clock)
    assert stuck.due(run, run.progress, empty=False) is False
    return clock, run, stuck


def held_at(run: FakeRun, stuck: Stuck, inputs: int, new_at: Collection[int] = ()) -> list[int]:
    """Add ``inputs`` inputs one by one, the run's input numbered in ``new_at`` covering a new
    line and each other only line 1, and hold each moment due after one; the run's inputs at
    each moment."""
    held: list[int] = []
    for _ in range(inputs):
        number = len(run.records) + 1
        run.add(number if number in new_at else 1)
        if stuck.due(run, run.progress, empty=False):
            stuck.hold(run)
            held.append(len(run.records))
    return held


# space-out-stuck-moments-that-ask-nothing-the-wait-doubles
def test_moments_that_ask_nothing_wait_5_10_20_then_40_inputs() -> None:
    _, run, stuck = seeded([False])

    assert held_at(run, stuck, 80) == [6, 16, 36, 76]


# space-out-stuck-moments-that-ask-nothing-a-new-line-resets
def test_an_input_that_covers_a_new_line_brings_the_wait_back_to_5() -> None:
    _, run, stuck = seeded([False])

    # input 9 covers line 9: 5 inputs after it, not 10 after the moment at 6
    assert held_at(run, stuck, 30, new_at={9}) == [6, 14, 24]


# space-out-stuck-moments-that-ask-nothing-a-new-line-resets
def test_a_moment_s_own_input_that_covers_a_new_line_brings_the_wait_back_to_5() -> None:
    _, run, stuck = seeded([False], covers=50)

    # the first moment asks nothing and runs input 7, which covers line 50: the next comes 5
    # inputs after it, not 10
    assert held_at(run, stuck, 20) == [7, 12, 22]


# space-out-stuck-moments-that-ask-nothing-the-wait-doubles
def test_a_no_fork_moment_that_asks_nothing_doubles_the_wait() -> None:
    _, run, stuck = seeded([False])
    assert stuck.due(run, run.progress, empty=True) is True
    stuck.hold(run)

    # 10 inputs after the no-fork moment, which ended after input 1, not 5
    assert held_at(run, stuck, 12) == [11]


# space-out-stuck-moments-that-ask-nothing-an-ask-resets
def test_a_moment_that_asks_brings_the_wait_back_to_5_and_counts_toward_three() -> None:
    _, run, stuck = seeded([False, False, True, True, True, False])

    # the moment at 36 asks, so the next waits 5; after 3 that asked, none comes
    assert held_at(run, stuck, 80) == [6, 16, 36, 41, 46]


# space-out-stuck-moments-that-ask-nothing-the-stretch-doubles
def test_a_moment_that_asks_nothing_doubles_the_stretch_until_a_new_line() -> None:
    clock, run, stuck = seeded([False], Bounds(until=1000.0, budget=BUDGET))
    quarter = BUDGET / 4

    def due_at(now: float) -> bool:
        clock.now = now
        return stuck.due(run, run.progress, empty=False)

    held = 0.0
    # the fourth, twice the budget, is one no run reaches: its budget's clock holds less
    for stretch in (quarter, 2 * quarter, BUDGET, 2 * BUDGET):
        assert due_at(held + stretch - 0.1) is False
        assert due_at(held + stretch) is True
        stuck.hold(run)
        held += stretch
    run.add(5)

    assert due_at(held) is False
    assert due_at(held + quarter - 0.1) is False
    assert due_at(held + quarter) is True


# space-out-stuck-moments-that-ask-nothing-an-ask-resets
def test_a_moment_that_asks_brings_the_stretch_back_to_a_quarter() -> None:
    clock, run, stuck = seeded([False, True], Bounds(until=1000.0, budget=BUDGET))
    quarter = BUDGET / 4

    def due_at(now: float) -> bool:
        clock.now = now
        return stuck.due(run, run.progress, empty=False)

    # the moment at a quarter asks nothing, so the next waits a half; that one asks
    for now in (quarter, 3 * quarter):
        assert due_at(now) is True
        stuck.hold(run)

    assert due_at(4 * quarter - 0.1) is False
    assert due_at(4 * quarter) is True

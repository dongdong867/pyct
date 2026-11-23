"""A run is also stuck when a share of its budget passes with no new line, counted on the
budget's clock, which a wait for the model pauses; each test moves a clock of its own."""

from dataclasses import dataclass, field

from pyct.binding.bind import Seed
from pyct.results.causes import Reason, WhyEntry
from pyct.results.coverage import Progress, Reach, Scope
from pyct.results.record import InputRecord, Stop
from pyct.run.bounds import Bounds
from pyct.run.stuck import MOMENTS, STRETCH_SHARE, Handled, Kind, Moment, Outcome, Stuck

FILE = "m.py"
BUDGET = 40.0
# a quarter of the budget: 10 s
STRETCH = BUDGET * STRETCH_SHARE
HANDLER = WhyEntry(FILE, (9,), Reason.HANDLER)


@dataclass
class Clock:
    """A clock that stands still until a test moves it."""

    now: float = 0.0

    def __call__(self) -> float:
        return self.now


@dataclass
class FakeRun:
    """A run part way through, with one line missed, whose inputs a test adds one by one."""

    bounds: Bounds = field(default_factory=lambda: Bounds(until=BUDGET, budget=BUDGET))
    records: list[InputRecord] = field(default_factory=list)
    stopped: Stop | None = None
    progress: Progress = field(
        default_factory=lambda: Progress(Scope(FILE, frozenset({1, 2, 3, 9})), frozenset())
    )

    def add(self, *lines: int) -> None:
        """Keep an input that covered ``lines``."""
        covered = frozenset(lines)
        self.progress.add(covered, Reach())
        self.records.append(InputRecord(args={}, forks=(), covered_lines=covered))

    def causes(self, stop_at: float | None) -> tuple[WhyEntry, ...]:
        return (HANDLER,)

    def run_input(self, seed: Seed, source: object, wanted: object = None) -> InputRecord | Stop:
        raise AssertionError("no fake tool here runs an input")

    def tell_ask(self, ask: object) -> None:
        pass

    def pause(self, seconds: float) -> None:
        self.bounds = self.bounds.paused(seconds)


@dataclass
class Waiting:
    """A tool that asks at each moment and waits ``waits`` seconds of ``clock`` for the model,
    pausing the run's clock for them, as a tool does."""

    clock: Clock
    waits: float = 0.0
    kind: Kind = Kind.GUESSES
    can_ask: bool = True
    moments: int = 0

    def take(self, entries: tuple[WhyEntry, ...], moment: Moment) -> Handled:
        self.moments += 1
        self.clock.now += self.waits
        moment.run.pause(self.waits)
        return Handled(tuple(Outcome.SKIPPED for _ in entries), asked=True)

    def heard(self, record: InputRecord, number: int) -> None:
        pass

    def waiting(self, moment: Moment) -> bool:
        return False


def stuck_at(clock: Clock, run: FakeRun, stuck: Stuck, now: float) -> bool:
    """Whether a moment comes at ``now``, with a fork still left to flip."""
    clock.now = now
    return stuck.due(run, run.progress, empty=False)


def seeded(waits: float = 0.0, until: float = BUDGET) -> tuple[Clock, FakeRun, Stuck]:
    """A run whose one seed covered lines 1 and 2, first looked at as its seed ended, at 0."""
    clock = Clock()
    run = FakeRun(bounds=Bounds(until=until, budget=BUDGET))
    run.add(1, 2)
    stuck = Stuck([Waiting(clock, waits)], clock)
    assert stuck_at(clock, run, stuck, 0.0) is False
    return clock, run, stuck


def test_a_quarter_of_the_budget_with_no_new_line_makes_a_run_stuck() -> None:
    clock, run, stuck = seeded()

    assert stuck_at(clock, run, stuck, STRETCH - 0.1) is False
    assert stuck_at(clock, run, stuck, STRETCH) is True


def test_the_stretch_holds_with_fewer_than_five_inputs_and_none_at_all() -> None:
    clock, run, stuck = seeded()
    run.add(1)

    assert stuck_at(clock, run, stuck, STRETCH) is True


def test_an_input_that_covers_a_new_line_starts_the_stretch_again() -> None:
    clock, run, stuck = seeded()
    clock.now = 8.0
    run.add(3)

    assert stuck_at(clock, run, stuck, 8.0) is False
    assert stuck_at(clock, run, stuck, 8.0 + STRETCH - 0.1) is False
    assert stuck_at(clock, run, stuck, 8.0 + STRETCH) is True


def test_an_input_that_covers_only_lines_covered_before_does_not() -> None:
    clock, run, stuck = seeded()
    clock.now = 8.0
    run.add(1, 2)

    assert stuck_at(clock, run, stuck, STRETCH) is True


def test_the_stretch_starts_again_as_the_pass_after_a_new_line_s_input_starts() -> None:
    # the input that covered line 3 is looked at as the next pass starts, at 8 s
    clock, run, stuck = seeded()
    run.add(3)

    assert stuck_at(clock, run, stuck, 8.0) is False
    assert stuck_at(clock, run, stuck, 8.0 + STRETCH - 0.1) is False


def test_the_stretch_counts_again_from_the_moment_s_end_after_the_model_s_wait() -> None:
    clock, run, stuck = seeded(waits=30.0)
    assert stuck_at(clock, run, stuck, STRETCH) is True

    stuck.hold(run)

    # the moment waited 30 s for the model and ended at 40 s on the clock
    assert stuck_at(clock, run, stuck, STRETCH + 30.0 + STRETCH - 0.1) is False
    assert stuck_at(clock, run, stuck, STRETCH + 30.0 + STRETCH) is True


def test_a_wait_paused_within_the_stretch_does_not_count() -> None:
    clock, run, stuck = seeded()
    clock.now = 5.0
    # 30 s waiting for the model, which the budget's clock does not count
    run.pause(30.0)

    assert stuck_at(clock, run, stuck, 30.0 + STRETCH - 0.1) is False
    assert stuck_at(clock, run, stuck, 30.0 + STRETCH) is True


def test_a_run_with_no_budget_is_not_stuck_on_time() -> None:
    clock = Clock()
    run = FakeRun(bounds=Bounds())
    run.add(1, 2)
    stuck = Stuck([Waiting(clock)], clock)

    assert stuck_at(clock, run, stuck, 0.0) is False
    assert stuck_at(clock, run, stuck, 1e9) is False


def test_moments_on_time_count_toward_the_three_that_ask() -> None:
    clock, run, stuck = seeded(until=1000.0)
    now = 0.0
    for _ in range(MOMENTS):
        now += STRETCH
        assert stuck_at(clock, run, stuck, now) is True
        stuck.hold(run)

    assert stuck_at(clock, run, stuck, now + STRETCH) is False


def test_no_moment_comes_on_time_once_the_budget_is_spent() -> None:
    clock, run, stuck = seeded()

    assert stuck_at(clock, run, stuck, BUDGET) is False

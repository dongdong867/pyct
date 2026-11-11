"""A caller of run() gives it several seeds: each runs, in order, before any solver input."""

import dataclasses
import time
from collections import deque

import pytest

from pyct.binding.bind import Seed
from pyct.config.goal import Goal
from pyct.config.limits import Limits
from pyct.config.plateau import Plateau
from pyct.results.coverage import Progress, Reach, Scope
from pyct.results.failure import FailureKind
from pyct.results.record import InputRecord, Source, Stop, StopKind
from pyct.run.isolation import Isolation
from pyct.run.process import InputStartError
from pyct.run.run import Attempt, Bounds, Start, _covered_or_plateau, _seed_attempt, run
from pyct.run.setup import Setup
from pyct.run.target import load_target

# `bucket(x)`: x < 100, then x < 10 under it; 5, 50 and 500 take its three paths
BUCKET = "targets.flip.nested_checks::bucket"
# `echo(x)`: no fork at all
NO_CHECK = "targets.flip.no_check::echo"
# `three_deep(x)`: 30 and 31 take every check's true side, and no flip covers a new line
THREE_DEEP = "targets.flip.flips_gain_nothing::three_deep"
# `probe(x)`: raises below 10
RAISES = "targets.flip.raises_after_a_check::probe"


def no_input_yet() -> Progress:
    return Progress(Scope(file="", lines=frozenset()), frozenset())


def sources(records: tuple[InputRecord, ...]) -> list[Source]:
    return [record.source for record in records]


def xs(records: tuple[InputRecord, ...]) -> list[object]:
    return [record.args["x"] for record in records]


# run-from-several-seeds-through-run
def test_each_seed_runs_in_order_before_any_solver_input() -> None:
    result = run(
        load_target(BUCKET), [{"x": 5}, {"x": 500}], setup=Setup(isolation=Isolation.IN_PROCESS)
    )

    assert xs(result.records[:2]) == [5, 500]
    assert sources(result.records) == [Source.SEED, Source.SEED, Source.SOLVER]


# run-from-several-seeds-one-tree
def test_the_solver_starts_from_every_seed_s_path() -> None:
    result = run(
        load_target(BUCKET), [{"x": 5}, {"x": 500}], setup=Setup(isolation=Isolation.IN_PROCESS)
    )

    # the seeds took two of the three paths, so one solver input takes the third
    assert len(result.records) == 3
    solved = result.records[2].args["x"]
    assert isinstance(solved, int)
    assert 10 <= solved < 100
    # every fork of the three paths has run both ways
    assert result.stopped == Stop(StopKind.NO_FORK)


def test_one_seed_still_runs_as_a_mapping() -> None:
    result = run(load_target(BUCKET), {"x": 5}, setup=Setup(isolation=Isolation.IN_PROCESS))

    assert sources(result.records)[0] is Source.SEED
    assert sources(result.records)[1:] == [Source.SOLVER] * (len(result.records) - 1)


def test_a_run_with_no_seed_is_refused() -> None:
    with pytest.raises(ValueError, match="at least one seed"):
        run(load_target(BUCKET), [], setup=Setup(isolation=Isolation.IN_PROCESS))


# run-from-several-seeds-waiting-seed-is-work
def test_a_waiting_seed_keeps_the_run_from_stopping_on_no_fork() -> None:
    result = run(
        load_target(NO_CHECK),
        [{"x": 1}, {"x": 2}, {"x": 3}],
        limits=Limits(goal=Goal.BUGS),
        setup=Setup(isolation=Isolation.IN_PROCESS),
    )

    assert xs(result.records) == [1, 2, 3]
    assert result.stopped == Stop(StopKind.NO_FORK)


# run-from-several-seeds-plateau-after-the-seeds
def test_the_plateau_counts_from_the_first_input_after_the_seeds() -> None:
    result = run(
        load_target(THREE_DEEP),
        [{"x": 30}, {"x": 31}],
        limits=Limits(plateau=Plateau(inputs=1)),
        setup=Setup(isolation=Isolation.IN_PROCESS),
    )

    # the second seed covered no new line, and the solver still gets its turn
    assert sources(result.records) == [Source.SEED, Source.SEED, Source.SOLVER]
    assert result.stopped == Stop(StopKind.NO_GAIN, plateau=1)


# run-from-several-seeds-full-coverage-skips-the-rest
def test_full_coverage_stops_the_seeds_still_waiting() -> None:
    result = run(
        load_target(BUCKET),
        [{"x": 5}, {"x": 50}, {"x": 500}, {"x": 7}],
        setup=Setup(isolation=Isolation.IN_PROCESS),
    )

    assert xs(result.records) == [5, 50, 500]
    assert result.stopped == Stop(StopKind.FULL)


def test_the_bugs_goal_runs_every_seed_past_full_coverage() -> None:
    result = run(
        load_target(BUCKET),
        [{"x": 5}, {"x": 50}, {"x": 500}, {"x": 7}],
        limits=Limits(goal=Goal.BUGS),
        setup=Setup(isolation=Isolation.IN_PROCESS),
    )

    assert xs(result.records) == [5, 50, 500, 7]
    assert result.stopped == Stop(StopKind.NO_FORK)


# run-from-several-seeds-a-raise-goes-on
def test_a_seed_that_raises_does_not_stop_the_seeds() -> None:
    result = run(
        load_target(RAISES), [{"x": 1}, {"x": 20}], setup=Setup(isolation=Isolation.IN_PROCESS)
    )

    assert xs(result.records[:2]) == [1, 20]
    failure = result.records[0].failure
    assert failure is not None
    assert failure.kind is FailureKind.TARGET_RAISED
    assert result.records[1].failure is None


def refused(args: object, until: float | None) -> object:
    raise InputStartError("could not start a child process: refused")


def test_a_later_seed_that_cannot_start_stops_the_run() -> None:
    waiting = deque([Start(Seed.of({"x": 2}))])

    attempt = _seed_attempt(refused, waiting, Bounds(), no_input_yet())  # pyrefly: ignore[bad-argument-type]

    assert attempt == Attempt(
        stop=Stop(StopKind.COULD_NOT_START, "could not start a child process: refused")
    )


def test_a_waiting_seed_does_not_run_once_the_budget_is_spent() -> None:
    waiting = deque([Start(Seed.of({"x": 2}))])
    spent = Bounds(until=time.monotonic() - 1)

    attempt = _seed_attempt(refused, waiting, spent, no_input_yet())  # pyrefly: ignore[bad-argument-type]

    assert attempt == Attempt(stop=Stop(StopKind.BUDGET))


def test_no_seed_pass_once_no_seed_waits() -> None:
    assert _seed_attempt(refused, deque(), Bounds(), no_input_yet()) is None  # pyrefly: ignore[bad-argument-type]


def test_one_seed_that_gains_nothing_still_gives_the_solver_a_turn() -> None:
    # a seed that covers no line in scope, as a function from another file covers none
    progress = no_input_yet()
    progress.add(frozenset(), Reach())

    assert _covered_or_plateau(Bounds(plateau=1, seeds=1), progress) is None
    progress.add(frozenset(), Reach())
    assert _covered_or_plateau(Bounds(plateau=1, seeds=1), progress) == Stop(
        StopKind.NO_GAIN, plateau=1
    )


def test_one_seed_that_covers_no_line_in_scope_still_gives_the_solver_a_turn() -> None:
    target = load_target(BUCKET)
    # measured against another module, as a function another file defines is: no input covers
    # a line in scope, so only the plateau ends the run
    elsewhere = dataclasses.replace(target, file=load_target(NO_CHECK).file)

    result = run(
        elsewhere,
        {"x": 5},
        limits=Limits(plateau=Plateau(inputs=1)),
        setup=Setup(isolation=Isolation.IN_PROCESS),
    )

    assert sources(result.records) == [Source.SEED, Source.SOLVER]
    assert result.stopped == Stop(StopKind.NO_GAIN, plateau=1)

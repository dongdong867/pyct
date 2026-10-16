"""The run stops once every line and branch is covered, unless its limits say to go past it."""

import pytest

from pyct.config.limits import Limits
from pyct.config.plateau import Plateau
from pyct.results.coverage import Reach
from pyct.results.record import Stop, StopKind
from pyct.run.isolation import Isolation
from pyct.run.run import run
from pyct.run.target import load_target

# `check(s)`: line 2 `if s.startswith("long"):` leads to line 3 and line 5; line 3 forks on its own
# line; line 4 raises
RAISES_LAST = "targets.stop.raises_last::check"
# `count(s)`: a seed of "xx" covers every line, and an input that covers no line after it can
# still send a branch the other way
COUNT_X = "targets.stop.count_x::count"


@pytest.mark.parametrize("isolation", [Isolation.IN_PROCESS, Isolation.AUTO])
def test_run_stops_once_every_line_and_branch_is_covered(isolation: Isolation) -> None:
    result = run(load_target(RAISES_LAST), {"s": ""}, isolation=isolation)

    # the fork on line 3 is still open, and the run stops all the same
    assert result.stopped == Stop(StopKind.FULL)
    assert len(result.records) == 2
    assert result.coverage.uncovered == {load_target(RAISES_LAST).file: frozenset()}


def test_run_goes_past_full_coverage_when_its_limits_say_so() -> None:
    limits = Limits(past_full_coverage=True)

    result = run(load_target(RAISES_LAST), {"s": ""}, limits=limits)

    assert result.stopped == Stop(StopKind.NO_FORK)
    assert len(result.records) > 2


def test_the_stop_on_full_coverage_comes_before_the_plateau() -> None:
    limits = Limits(plateau=Plateau(inputs=1))

    result = run(load_target(COUNT_X), {"s": "xx"}, limits=limits)

    # the last input covered no line the seed had not, and the plateau of 1 holds too
    assert result.stopped == Stop(StopKind.FULL)
    assert not result.records[-1].covered_lines - result.records[0].covered_lines
    past = run(
        load_target(COUNT_X),
        {"s": "xx"},
        limits=Limits(plateau=Plateau(inputs=1), past_full_coverage=True),
    )
    assert past.stopped == Stop(StopKind.NO_GAIN, plateau=1)


@pytest.mark.parametrize("isolation", [Isolation.IN_PROCESS, Isolation.AUTO])
def test_each_record_carries_what_its_input_reached(isolation: Isolation) -> None:
    result = run(load_target(RAISES_LAST), {"s": ""}, isolation=isolation)

    seed, raised = result.records
    assert seed.reach.went == {(2, 5)}
    assert seed.reach.branches == {2: {3, 5}}
    assert {2, 3, 4, 5} <= seed.reach.function_lines
    assert raised.reach == Reach(
        seed.reach.function_lines, seed.reach.branches, frozenset({(2, 3)})
    )


def test_the_words_of_the_stop() -> None:
    assert Stop(StopKind.FULL).reason == "every line and branch covered"

"""A run's why_uncovered: its tries gathered from misses, aimed inputs and untried forks."""

import dataclasses
from pathlib import Path

import pytest

from pyct.core.branch import Branch, Fact, ForkSite, Site
from pyct.results import record
from pyct.results.coverage import Coverage
from pyct.results.graphs import LONGEST_STRETCH, OutOfTimeError, Pace
from pyct.results.record import (
    Aim,
    Environment,
    InputRecord,
    Miss,
    MissWhy,
    RunResult,
    Source,
    Stop,
    StopKind,
)
from pyct.results.why import Condition, Reason, Run, Tries, WhyEntry

ENVIRONMENT = Environment(python="3.12.0", cvc5=None, platform="p", isolated=True)
SOURCE = """\
def same(x):
    # nothing is ever unequal to itself
    if x != x:
        return "never"
    return "always"
"""


def run_of(file: str, site: Site) -> RunResult:
    """A run of ``same``: the seed, one input that left its plan, one that kept it, and misses."""
    seed = InputRecord(
        args={"x": 1},
        forks=(Branch(expression=["!=", "x", "x"], taken=False, site=site),),
        covered_lines=frozenset({3, 5}),
    )
    aimed = Aim(site=site, position=0)
    left = dataclasses.replace(seed, source=Source.SOLVER, aim=aimed, mismatch_at=0)
    followed = dataclasses.replace(seed, forks=(), source=Source.SOLVER, aim=aimed)
    elsewhere = Site(file=file, line=9, col=0)
    misses = (
        Miss(site, MissWhy.UNKNOWN, raising=True),
        Miss(site, MissWhy.UNSAT),
        Miss(site, MissWhy.TIMEOUT),
        Miss(elsewhere, MissWhy.UNKNOWN),
    )
    return RunResult(
        entry="m::same",
        records=(seed, left, followed),
        coverage=Coverage(covered={file: frozenset({3, 5})}, lines={file: frozenset({1, 3, 4, 5})}),
        stopped=Stop(kind=StopKind.BUDGET),
        environment=ENVIRONMENT,
        misses=misses,
        untried={ForkSite(site): 2, ForkSite(site, raising=True): 1},
    )


def test_the_tries_at_a_condition_count_every_way_the_run_could_have_flipped_it(
    tmp_path: Path,
) -> None:
    file = tmp_path / "m.py"
    file.write_text(SOURCE)
    site = Site(file=str(file), line=3, col=7)

    result = run_of(str(file), site)

    # an input that followed its plan took the side, so only the one that left it counts; what
    # the run tried at an operation's fork at the same column is that fork's, not the test's
    assert result.why_uncovered == (
        WhyEntry(file=str(file), lines=(1,), reason=Reason.IMPORT),
        WhyEntry(
            file=str(file),
            lines=(4,),
            reason=Reason.NOT_TAKEN,
            condition=Condition(site=site, side=True),
            tries=Tries(not_tried=2, unsat=1, timeout=1, left_the_plan=1),
        ),
    )
    # worked out once, on the first read
    assert result.why_uncovered is result.why_uncovered


def test_a_decided_check_shows_its_side_and_counts_once_an_input(tmp_path: Path) -> None:
    file = tmp_path / "m.py"
    file.write_text(SOURCE)
    site = Site(file=str(file), line=3, col=7)
    # `x != x` decided false, twice on one input, and a place no check holds beside it
    decided = Fact(["!=", "x", "x"], False, site)
    seed = InputRecord(
        args={"x": 1},
        forks=(),
        covered_lines=frozenset({3, 5}),
        facts=(decided, decided, Fact(None, True, Site(str(file), 5, 4), place=["walked"])),
    )
    result = RunResult(
        entry="m::same",
        records=(seed, dataclasses.replace(seed, args={"x": 2})),
        coverage=Coverage(
            covered={str(file): frozenset({3, 5})}, lines={str(file): frozenset({1, 3, 4, 5})}
        ),
        stopped=Stop(kind=StopKind.NO_FORK),
        environment=ENVIRONMENT,
    )

    assert result.why_uncovered[1] == WhyEntry(
        file=str(file),
        lines=(4,),
        reason=Reason.NOT_TAKEN,
        condition=Condition(site=site, side=True),
        tries=Tries(decided=2),
    )


def test_the_analysis_stops_so_its_longest_stretch_still_ends_within_the_grace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    file = tmp_path / "m.py"
    file.write_text(SOURCE)
    run = dataclasses.replace(run_of(str(file), Site(str(file), 3, 7)), deadline=100.0)
    stops: list[float | None] = []

    def explained(
        _file: str, _uncovered: object, _covered: object, given: Run
    ) -> tuple[WhyEntry, ...]:
        stops.append(given.stop_at)
        return ()

    monkeypatch.setattr(record, "explain", explained)

    assert run.why_uncovered == ()
    # the stop is seen at the first clock read past it, at most one stretch later
    [stop_at] = stops
    assert stop_at is not None
    assert stop_at + LONGEST_STRETCH <= 100.0 + record.ANALYSIS_GRACE


def test_a_run_read_past_the_analysis_stop_reads_no_input_and_no_try(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    file = tmp_path / "m.py"
    file.write_text(SOURCE)
    # a run whose deadline is long past: no cause can be worked out in the time left
    run = dataclasses.replace(run_of(str(file), Site(str(file), 3, 7)), deadline=0.0)

    def never(_result: RunResult) -> object:
        raise AssertionError("the tries are read")

    monkeypatch.setattr(record, "_tries", never)

    assert run.why_uncovered == (
        WhyEntry(file=str(file), lines=(1, 4), reason=Reason.NOT_WORKED_OUT),
    )


def test_the_tries_look_at_the_clock_as_they_read_each_input_s_facts(tmp_path: Path) -> None:
    site = Site(file=str(tmp_path / "m.py"), line=3, col=7)
    # far past the steps the analysis takes between two looks at the clock, on one input
    facts = (Fact(["!=", "x", "x"], False, site),) * 10_000
    seed = InputRecord(args={"x": 1}, forks=(), covered_lines=frozenset(), facts=facts)
    result = RunResult(
        entry="m::same",
        records=(seed,),
        coverage=Coverage(covered={}, lines={}),
        stopped=Stop(kind=StopKind.NO_FORK),
        environment=ENVIRONMENT,
    )

    with pytest.raises(OutOfTimeError):
        record._tries(result, Pace(lambda _ahead: True))

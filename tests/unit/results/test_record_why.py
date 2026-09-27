"""A run's why_uncovered: its tries gathered from misses, aimed inputs and untried forks."""

import dataclasses
from pathlib import Path

from pyct.core.branch import Branch, ForkSite, Site
from pyct.results.coverage import Coverage
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
from pyct.results.why import Condition, Reason, Tries, WhyEntry

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
        untried=(ForkSite(site), ForkSite(site), ForkSite(site, raising=True)),
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

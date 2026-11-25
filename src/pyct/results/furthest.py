"""The way to one missed line, and the input that got furthest along it: what a guess ask sends."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pyct.core.foundation.branch import Site
from pyct.results.blocks import StepKind
from pyct.results.causes import Condition
from pyct.results.record import InputRecord
from pyct.results.why import Run, Walked, along

# the most conditions a way holds; the ones nearest the line are kept
MOST_CONDITIONS = 30


@dataclass(frozen=True)
class Way:
    """The conditions on a missed line's way, each with the side the line needs, in the order a
    run meets them, and the number from 1 of the input that got furthest along it.

    ``furthest`` is None when no input passed a node on the way, or when the stop came first.
    """

    conditions: tuple[Condition, ...] = ()
    furthest: int | None = None


def way_to(file: str, line: int, records: Sequence[InputRecord], stop_at: float | None) -> Way:
    """The way to ``line`` of ``file`` as the inputs that ran show it, its raising steps left out.

    ``stop_at`` is the monotonic instant past which no more of it is worked
    out, or None to work it all out, as for ``why_uncovered``.
    """
    walked = [
        Walked(record.forks, record.failure is not None, record.covered_lines, record.facts)
        for record in records
    ]
    found = along(file, line, Run(walked, {}, stop_at=stop_at))
    conditions = [
        Condition(Site(file=file, line=step.line, col=step.col), step.side)
        for step in found.steps
        if step.kind is StepKind.CONDITION and not step.raising
    ]
    return Way(tuple(conditions[-MOST_CONDITIONS:]), found.furthest)

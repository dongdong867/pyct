"""The path to ask the solver for: one fork of a run taken the other way."""

import dataclasses
from dataclasses import dataclass

from pyct.core.branch import Branch
from pyct.results.record import Aim


@dataclass(frozen=True)
class Plan:
    """The path the next input should take, and the fork it is aimed at."""

    prefix: tuple[Branch, ...]
    aim: Aim


def plan(forks: tuple[Branch, ...]) -> Plan | None:
    """The path of ``forks`` with its last fork taken the other way.

    The last fork is the one nothing else on the path depends on, so
    flipping it asks for the shortest new path. A run that forked nowhere
    has nothing to ask about.
    """
    if not forks:
        return None
    last = forks[-1]
    flipped = dataclasses.replace(last, taken=not last.taken)
    return Plan(prefix=(*forks[:-1], flipped), aim=Aim(site=last.site, position=len(forks) - 1))

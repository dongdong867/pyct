"""The path to ask the solver for: one fork of a run taken the other way."""

import dataclasses
from dataclasses import dataclass

from pyct.core.branch import Branch
from pyct.results.record import Aim


@dataclass(frozen=True)
class Plan:
    """The path the next input should take, the fork it is aimed at, and whose path it extends.

    ``path`` counts the paths in the order the tree took them, the seed's first, so it names
    the input whose path this is, which the answer starts from.
    """

    prefix: tuple[Branch, ...]
    aim: Aim
    path: int = 0


def plan(forks: tuple[Branch, ...], path: int = 0) -> Plan | None:
    """The path of ``forks`` with its last fork taken the other way.

    The last fork is the one nothing else on the path depends on, so
    flipping it asks for the shortest new path. A run that forked nowhere
    has nothing to ask about.
    """
    if not forks:
        return None
    last = forks[-1]
    # what the input kept once the fork went its way does not hold on the other side
    flipped = dataclasses.replace(last, taken=not last.taken, holds=None)
    aim = Aim(site=last.site, position=len(forks) - 1)
    return Plan(prefix=(*forks[:-1], flipped), aim=aim, path=path)

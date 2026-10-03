"""The path to ask the solver for: one fork of a run taken the other way."""

import dataclasses
from dataclasses import dataclass

from pyct.core.branch import Branch, Fact
from pyct.results.record import Aim


@dataclass(frozen=True)
class Plan:
    """The path the next input should take, the fork it is aimed at, and whose path it extends.

    ``path`` counts the paths in the order the tree took them, the seed's first, so it names
    the input whose path this is, which the answer starts from. ``facts`` are what that path
    held before the aimed fork: each fact recorded after it is dropped, since it held only once
    the fork went the way the path took.
    """

    prefix: tuple[Branch, ...]
    aim: Aim
    path: int = 0
    facts: tuple[Fact, ...] = ()

    @property
    def asked(self) -> tuple[Branch | Fact, ...]:
        """The forks and the kept facts in the order the path recorded them, the flipped fork
        last: what the solver is asked for."""
        merged: list[Branch | Fact] = []
        facts = iter(self.facts)
        fact = next(facts, None)
        for position, fork in enumerate(self.prefix):
            while fact is not None and fact.after <= position:
                merged.append(fact)
                fact = next(facts, None)
            merged.append(fork)
        return tuple(merged)


def plan(forks: tuple[Branch, ...], path: int = 0, facts: tuple[Fact, ...] = ()) -> Plan | None:
    """The path of ``forks`` with its last fork taken the other way, and the facts it keeps.

    The last fork is the one nothing else on the path depends on, so
    flipping it asks for the shortest new path. A run that forked nowhere
    has nothing to ask about. A fact recorded before the last fork held on
    both its sides, as a key's place a lookup was given does; one recorded
    after it held only on the side the path took, so it is dropped.
    """
    if not forks:
        return None
    last = forks[-1]
    flipped = dataclasses.replace(last, taken=not last.taken)
    aim = Aim(site=last.site, position=len(forks) - 1, raising=last.raising)
    kept = tuple(fact for fact in facts if fact.after < len(forks))
    return Plan(prefix=(*forks[:-1], flipped), aim=aim, path=path, facts=kept)

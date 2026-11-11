"""The ask on the same path: what a rewrite's run recorded, put where the condition sat in a
plan's ask, and whether an input took the side the condition's missed line needs.

The ask holds the path's forks and facts as the plan holds them, each fork
at the condition's site and side replaced by what the rewrite recorded on
the input that path extends: its own forks and facts as they went there,
each operation's fork before a raise kept on the side that did not raise,
and its own branch taken true. The plan's aimed fork is one of them, so the
original condition, whose ask ran out, is left out.
"""

from __future__ import annotations

import dataclasses
import types
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from pyct.binding.bind import Seed
from pyct.branches.plan import Plan
from pyct.core.foundation.branch import Branch, Fact
from pyct.execution.execute import ExecutionResult
from pyct.results.causes import Condition
from pyct.results.failure import FailureKind
from pyct.results.record import Aim, InputRecord, MissWhy, Stop
from pyct.rewrite.condition import HELD_COL, HELD_LINE

# why a rewrite that records no fork of its own and no downgrade is refused
READS_NO_ARGUMENT = "it reads no argument"

# runs a rewrite's code in a child of pyct's process on an input's arguments: what the call
# recorded, or why it did not run
type RunRewrite = Callable[[types.CodeType, Mapping[str, object]], ExecutionResult | str]

# runs a real input aimed at a plan, as the loop runs every input: its record, or the stop it met
type RunInput = Callable[[Seed, Plan], InputRecord | Stop]


@dataclass(frozen=True)
class GivenUp:
    """A condition the solver gave up on: the first plan aimed at it whose ask ended in
    ``timeout`` or ``unknown``, the input whose path that plan extends, and the answer."""

    condition: Condition
    plan: Plan
    origin: Seed
    answer: MissWhy


@dataclass(frozen=True)
class Recorded:
    """What a rewrite's run on an input puts in an ask, in the order it recorded it, its own
    branch taken true, and whether the input already took that branch's true side (``met``)."""

    items: tuple[Branch | Fact, ...]
    met: bool


def recorded(result: ExecutionResult, file: str) -> Recorded | str:
    """What a rewrite's run on an input puts in an ask, or why the run gives none: it raised or
    did not finish, pyct followed no value through an operation, or it read no argument."""
    if result.failure is not None:
        failure = result.failure
        verb = "raised" if failure.kind is FailureKind.TARGET_RAISED else "did not finish"
        return f"it {verb} on the input: {failure.detail}"
    own = [
        at
        for at, fork in enumerate(result.branches)
        if fork.site.file == file
        and (fork.site.line, fork.site.col) == (HELD_LINE, HELD_COL)
        and not fork.raising
    ]
    if not own:
        names = list(dict.fromkeys(entry.name for entry in result.downgrades))
        return f"pyct does not follow {', '.join(names)}" if names else READS_NO_ARGUMENT
    last = result.branches[own[-1]]
    forks = (*result.branches[: own[-1]], dataclasses.replace(last, taken=True))
    # a plan only to merge the facts in among the forks; nothing aims at its aim
    aim = Aim(last.site, len(forks) - 1)
    return Recorded(Plan(forks, aim, facts=result.facts).asked, last.taken)


def holding(plan: Plan, condition: Condition) -> bool:
    """Whether the plan's ask holds the condition at its side, as its aim or an earlier fork."""
    return any(_at(fork, condition) for fork in plan.prefix)


def in_place(
    asked: tuple[Branch | Fact, ...], condition: Condition, items: tuple[Branch | Fact, ...]
) -> tuple[Branch | Fact, ...]:
    """The ask with each fork at the condition's site and side replaced by ``items``."""
    made: list[Branch | Fact] = []
    for item in asked:
        if isinstance(item, Branch) and _at(item, condition):
            made.extend(items)
        else:
            made.append(item)
    return tuple(made)


def takes(record: InputRecord, condition: Condition) -> bool:
    """Whether an input took the side the condition's missed line needs at any fork it recorded
    at the condition's site, even after it left the path."""
    return any(_at(fork, condition) for fork in record.forks)


def _at(fork: Branch, condition: Condition) -> bool:
    return not fork.raising and fork.site == condition.site and fork.taken == condition.side

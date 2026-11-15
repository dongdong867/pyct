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
from pyct.branches.compare import Parts, same_expression
from pyct.branches.plan import Plan
from pyct.core.foundation.branch import Branch, Fact
from pyct.execution.execute import ExecutionResult
from pyct.results.causes import Condition
from pyct.results.failure import FailureKind
from pyct.results.record import Aim, InputRecord, MissWhy, Stop
from pyct.rewrite.condition import HELD_COL, HELD_LINE

# why a rewrite that records no fork of its own and no downgrade is refused
READS_NO_ARGUMENT = "it reads no argument"

# the parts of expressions one plan's path may compare, over all its earlier forks, to tell
# whether it holds its aimed fork's check on the other side
PLAN_PARTS = 100_000

# runs a rewrite's code in a child of pyct's process on an input's arguments: what the call
# recorded, or why it did not run
type RunRewrite = Callable[[types.CodeType, Mapping[str, object]], ExecutionResult | str]

# runs a real input aimed at a plan, as the loop runs every input: its record, or the stop it met
type RunInput = Callable[[Seed, Plan], InputRecord | Stop]


# the visits kept for one condition: the first plans aimed at it whose asks gave up, a request
# is about the first, and a rewrite the solver gives no input for on one is tried on the next
VISITS = 3


@dataclass(frozen=True)
class Visit:
    """One plan aimed at a condition, and the input whose path that plan extends."""

    plan: Plan
    origin: Seed


@dataclass(frozen=True)
class GivenUp:
    """A condition the solver gave up on: the first plan aimed at it whose ask ended in
    ``timeout`` or ``unknown``, or had no time left after a kept rewrite's ask, the input whose
    path that plan extends, and the answer; and ``later``, the next such plans, in the order
    they gave up, up to ``VISITS`` in all. A plan whose path holds its own check on the other
    side (``holds_its_own_check``) is answered ``unsat`` before any ask in a run with rewrites,
    so it is never kept."""

    condition: Condition
    plan: Plan
    origin: Seed
    answer: MissWhy
    later: tuple[Visit, ...] = ()

    @property
    def visits(self) -> tuple[Visit, ...]:
        """Each kept plan with its input, in the order they gave up."""
        return (Visit(self.plan, self.origin), *self.later)

    def joined(self, visit: Visit) -> GivenUp:
        """This condition with ``visit`` kept last, while fewer than ``VISITS`` are kept."""
        if len(self.visits) >= VISITS:
            return self
        return dataclasses.replace(self, later=(*self.later, visit))


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


def holds_its_own_check(plan: Plan) -> bool:
    """Whether the path before the plan's aimed fork holds the same check on the other side: a
    fork at the aimed fork's site, of the same kind, taken the other way, whose expression is
    the same (``same_expression``). No input takes one check both ways on one path. False when
    the comparisons cannot tell within ``PLAN_PARTS`` compared parts."""
    aimed = plan.prefix[-1]
    parts = Parts(PLAN_PARTS)
    for fork in plan.prefix[:-1]:
        if fork.where != aimed.where or fork.taken == aimed.taken:
            continue
        same = same_expression(fork.expression, aimed.expression, parts)
        if same is None:
            return False
        if same:
            return True
    return False


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

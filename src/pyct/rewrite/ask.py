"""The ask of a rewrite alone: what a rewrite's run recorded, which the solver solves with none of
the path, and whether an input took the side the condition's missed line needs.

The ask holds the rewrite's own forks and facts as they went on the input
whose path the given-up plan extends, each operation's fork before a raise
kept on the side that did not raise, and its own branch taken true. It
holds none of the path's forks and none of pyct's facts at the condition's
place. What the rewrite's child recorded outside the rewrite's own code, as
it built the objects the rewrite reads fields of, is left out too. A kept
rewrite stands in for its condition in a later plan's ask on that plan's own
path (``in_place``, ``pyct.rewrite.kept``).
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
from pyct.rewrite.condition import HELD_COL, HELD_LINE, Rewrite
from pyct.rewrite.kinds import Kinds

# why a rewrite that records no fork of its own and no downgrade is refused
READS_NO_ARGUMENT = "it reads no argument"
# why a rewrite that reads fields records no fork of its own and no downgrade; the reason names
# the fields it read
READS_NO_INPUT = "it reads no value an input sets"

# the parts of expressions one plan's path may compare, over all its earlier forks, to tell
# whether it holds its aimed fork's check on the other side
PLAN_PARTS = 100_000


@dataclass(frozen=True)
class Unread:
    """A rewrite's run that pyct's field reader ended: why it read no field of an object."""

    reason: str


# runs a rewrite's code in a child of pyct's process on an input's arguments: what the call
# recorded, why the reader read no field, or why it did not run
type RunRewrite = Callable[[types.CodeType, Mapping[str, object]], ExecutionResult | Unread | str]

# runs a real input, aimed at a plan when one is given, as the loop runs every input: its record,
# or the stop it met
type RunInput = Callable[[Seed, Plan | None], InputRecord | Stop]


@dataclass(frozen=True)
class GivenUp:
    """A condition the solver gave up on: the first plan aimed at it whose ask ended in
    ``timeout``, ``unknown`` or ``unsat``, or had no time left after a kept rewrite's ask, the
    input whose path that plan extends, and the answer. A plan whose path holds its own check on
    the other side (``holds_its_own_check``) is answered ``unsat`` before any ask in a run with
    rewrites, so it is never kept.

    For a condition that recorded no fork, ``plan`` and ``answer`` are None,
    ``origin`` is an input that ran the condition, ``forks`` the forks that
    input took, ``lines`` the missed lines the condition's side guards, and
    ``path`` that input's place among the run's inputs, from 0, as
    ``Plan.path`` counts it.
    """

    condition: Condition
    plan: Plan | None
    origin: Seed
    answer: MissWhy | None
    forks: tuple[Branch, ...] = ()
    lines: tuple[int, ...] = ()
    path: int = 0

    @property
    def earlier(self) -> tuple[Branch, ...]:
        """The forks the plan's path took before its aimed fork, or with no plan ``forks``."""
        return self.forks if self.plan is None else self.plan.prefix[:-1]


@dataclass(frozen=True)
class Recorded:
    """What a rewrite's run on an input puts in an ask, in the order it recorded it, its own
    branch taken true, and whether the input already took that branch's true side (``met``)."""

    items: tuple[Branch | Fact, ...]
    met: bool


def recorded(result: ExecutionResult | Unread, rewrite: Rewrite) -> Recorded | str:
    """What a rewrite's run on an input puts in an ask, or why the run gives none: the reader
    read no field, it raised or did not finish, pyct followed no value through an operation, or
    it read no argument, or no value an input sets of the fields it reads. Only the forks and
    facts the rewrite's own code recorded go in."""
    if isinstance(result, Unread):
        return result.reason
    if result.failure is not None:
        failure = result.failure
        verb = "raised" if failure.kind is FailureKind.TARGET_RAISED else "did not finish"
        return f"it {verb} on the input: {failure.detail}"
    file = rewrite.code.co_filename
    own = [
        at
        for at, fork in enumerate(result.branches)
        if fork.site.file == file
        and (fork.site.line, fork.site.col) == (HELD_LINE, HELD_COL)
        and not fork.raising
    ]
    if not own:
        return _none_own(result, rewrite)
    last = result.branches[own[-1]]
    kept = [fork for fork in result.branches[: own[-1]] if fork.site.file == file]
    forks = (*kept, dataclasses.replace(last, taken=True))
    # a plan only to merge the facts in among the forks; nothing aims at its aim
    aim = Aim(last.site, len(forks) - 1)
    return Recorded(Plan(forks, aim, facts=_own_facts(result, file)).asked, last.taken)


def _none_own(result: ExecutionResult, rewrite: Rewrite) -> str:
    """Why a rewrite's run that recorded no fork of its own gives no ask."""
    names = list(dict.fromkeys(entry.name for entry in result.downgrades))
    if names:
        return f"pyct does not follow {', '.join(names)}"
    if rewrite.fields:
        return f"{READS_NO_INPUT}: {', '.join(rewrite.fields)}"
    return READS_NO_ARGUMENT


def _own_facts(result: ExecutionResult, file: str) -> tuple[Fact, ...]:
    """The facts the rewrite's own code recorded, each placed after the forks of its own code
    recorded before it."""
    own_before = [0]
    for fork in result.branches:
        own_before.append(own_before[-1] + (fork.site.file == file))
    return tuple(
        fact.placed_after(own_before[min(fact.after, len(result.branches))])
        for fact in result.facts
        if fact.site.file == file
    )


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


def run_on(
    rewrite: Rewrite, origin: Seed, run: RunRewrite, self_name: str | None = None
) -> ExecutionResult | Unread | str | None:
    """The rewrite run on an input's arguments: what the call recorded, why the reader read no
    field, or why it did not run; None, with nothing run, when the input lacks a name it reads,
    or that name does not have the kind there it had where the rewrite was checked, under the
    hints the input was made with and the method's ``self_name`` (``Kinds``): an object for a
    name it reads fields of, plain for any other."""
    args = origin.args
    if not Kinds.of_seed(origin, self_name).fit(args, rewrite.reads, rewrite.objects):
        return None
    return run(rewrite.code, rewrite.handed(args))


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


def reached(record: InputRecord, given: GivenUp) -> bool:
    """Whether an input counts for a condition: with a plan, it took the side the missed line
    needs (``takes``); with none, it ran a line of ``given.lines``."""
    if given.plan is None:
        return not record.covered_lines.isdisjoint(given.lines)
    return takes(record, given.condition)


def takes(record: InputRecord, condition: Condition) -> bool:
    """Whether an input took the side the condition's missed line needs at any fork it recorded
    at the condition's site, even after it left the path."""
    return any(_at(fork, condition) for fork in record.forks)


def _at(fork: Branch, condition: Condition) -> bool:
    return not fork.raising and fork.site == condition.site and fork.taken == condition.side

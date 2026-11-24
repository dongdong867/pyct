"""How long a pick's ask may take, and whether its site waits for the last picks, from the
answer it ended in."""

from __future__ import annotations

from pyct.branches.plan import Plan
from pyct.run.bounds import Bounds
from pyct.solver.answer import Answer, Timeout, Unknown

# the share of its limit an ask that answered `unknown` used, at least, for its site to wait as
# a timed-out one does: 2.5 s of the default 10 s
SLOW_UNKNOWN_SHARE = 0.25

# the share of the solver timeout an ask gets whose path holds a fork that reads a formula's
# value: a formula's terms can make the solver slow, and a share leaves time for the other asks
FORMULA_SHARE = 0.25


def solve_limit(bounds: Bounds, left: float | None, plan: Plan) -> float:
    """The seconds one solve gets: the solver timeout, or ``FORMULA_SHARE`` of it when a fork of
    ``plan``'s path reads a formula's value, and ``left`` when the budget has less.

    ``left`` is read once, before the budget check, so a solve always gets
    the same time the check found above zero.
    """
    limit = bounds.solver_timeout
    if any(fork.formulas for fork in plan.prefix):
        limit *= FORMULA_SHARE
    return limit if left is None else min(limit, left)


def site_waits(answer: Answer, seconds: float, limit: float) -> bool:
    """Whether the pick's site waits for the last picks (`Tree.ran_long`): its ask ran to its
    limit, or it answered ``unknown`` after at least a quarter of ``limit``. In a rewrites run
    the pick's ``seconds`` hold a kept rewrite's run and ask too.

    An ``unknown`` that slow at a site would likely be as slow at the next
    path's fork there, which is a new side and would be picked first on each
    path. A quicker ``unknown`` may belong to its one path. Decision
    fork-order-a-slow-unknown-waits-as-a-timeout-does.
    """
    if isinstance(answer, Unknown):
        return seconds >= limit * SLOW_UNKNOWN_SHARE
    return isinstance(answer, Timeout)

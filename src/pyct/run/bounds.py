"""When a run must stop: its deadline, plateau, solve limit and goal, as one value."""

from __future__ import annotations

import dataclasses
import time
from dataclasses import dataclass

from pyct.config.budget import Budget
from pyct.config.goal import Goal
from pyct.config.limits import Limits
from pyct.config.solver_timeout import DEFAULT_SECONDS


@dataclass(frozen=True)
class Bounds:
    """When the loop must stop asking, and how long one solve may take.

    The budget becomes an instant here, because the clock starts when the call
    does, not when the person typed the seconds. The solver timeout stays
    seconds, because each solve starts its own clock. ``goal`` says whether
    the loop stops once every line and branch is covered, and ``seeds`` how
    many inputs the plateau leaves out before it counts. All in one value,
    so the loop and each pass keep to five parameters.
    """

    until: float | None = None
    plateau: int | None = None
    solver_timeout: float = DEFAULT_SECONDS
    goal: Goal = Goal.COVERAGE
    seeds: int = 1

    @classmethod
    def of(cls, limits: Limits, seeds: int) -> Bounds:
        return cls(
            until=deadline_for(limits.budget),
            plateau=limits.plateau.inputs,
            solver_timeout=limits.solver_timeout.seconds,
            goal=limits.goal,
            seeds=seeds,
        )

    def paused(self, seconds: float) -> Bounds:
        """The bounds with the deadline ``seconds`` later: the clock paused for a wait that is
        not the run's own work, such as the LLM's answer. No deadline stays none."""
        until = None if self.until is None else self.until + seconds
        return dataclasses.replace(self, until=until)


def deadline_for(budget: Budget) -> float | None:
    """The monotonic instant the call must end by. No seconds, no deadline."""
    return None if budget.seconds is None else time.monotonic() + budget.seconds

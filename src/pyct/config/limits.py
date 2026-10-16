"""What bounds a run: how long it may take, how long it may go without gain, each solve, and
whether it goes on once every line and branch is covered."""

from dataclasses import dataclass, field

from pyct.config.budget import Budget
from pyct.config.plateau import Plateau
from pyct.config.solver_timeout import SolverTimeout


@dataclass(frozen=True)
class Limits:
    """The budget, the plateau, the solver timeout, and whether to go past full coverage, as one
    value.

    The budget and the plateau with nothing set are no limit of that kind.
    The solver timeout always holds, 10 seconds with nothing set, because no
    solve runs without a limit.

    One value rather than three keywords, so ``run()`` keeps to five
    parameters and a caller that bounds a run hands over one thing.
    ``Budget``, ``Plateau`` and ``SolverTimeout`` keep their names inside
    it: a budget is the run's seconds, a plateau is inputs, a solver timeout
    is one solve's seconds, and no word is made to mean another.

    ``past_full_coverage`` keeps the run going once every line and branch
    is covered; by default that stops it.
    """

    budget: Budget = field(default_factory=Budget)
    plateau: Plateau = field(default_factory=Plateau)
    solver_timeout: SolverTimeout = field(default_factory=SolverTimeout)
    past_full_coverage: bool = False

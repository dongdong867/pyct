"""What bounds a run: how long it may take, how long it may go without gain, and each solve."""

from dataclasses import dataclass, field

from pyct.config.budget import Budget
from pyct.config.plateau import Plateau
from pyct.config.solver_timeout import SolverTimeout


@dataclass(frozen=True)
class Limits:
    """The budget, the plateau, and the solver timeout, as one value.

    The budget and the plateau with nothing set are no limit of that kind.
    The solver timeout always holds, 10 seconds with nothing set, because no
    solve runs without a limit.

    One value rather than three keywords, so ``run()`` keeps to five
    parameters and a caller that bounds a run hands over one thing.
    ``Budget``, ``Plateau`` and ``SolverTimeout`` keep their names inside
    it: a budget is the run's seconds, a plateau is inputs, a solver timeout
    is one solve's seconds, and no word is made to mean another.
    """

    budget: Budget = field(default_factory=Budget)
    plateau: Plateau = field(default_factory=Plateau)
    solver_timeout: SolverTimeout = field(default_factory=SolverTimeout)

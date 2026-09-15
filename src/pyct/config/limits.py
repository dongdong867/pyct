"""What bounds a run: how long it may take, and how long it may go without gain."""

from dataclasses import dataclass, field

from pyct.config.budget import Budget
from pyct.config.plateau import Plateau


@dataclass(frozen=True)
class Limits:
    """The budget and the plateau, as one value. Each with nothing set is no limit of that kind.

    One value rather than two keywords, so ``run()`` keeps to five parameters
    and a caller that bounds a run hands over one thing. ``Budget`` and
    ``Plateau`` keep their names inside it: a budget is seconds, a plateau is
    inputs, and neither word is made to mean the other.
    """

    budget: Budget = field(default_factory=Budget)
    plateau: Plateau = field(default_factory=Plateau)

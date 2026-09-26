"""How long one solve may take."""

from dataclasses import dataclass

# decision solver-limit-ten-seconds-unless-the-budget-has-less
DEFAULT_SECONDS = 10.0


@dataclass(frozen=True)
class SolverTimeout:
    """The seconds each solve may take. There is no ``None``: every solve has a limit.

    The default is 10 seconds, by decision
    solver-limit-ten-seconds-unless-the-budget-has-less: one fork cvc5
    cannot answer would otherwise hang a run with no budget. One field, as
    ``Budget`` and ``Plateau`` are, so the limits read the same way.
    """

    seconds: float = DEFAULT_SECONDS

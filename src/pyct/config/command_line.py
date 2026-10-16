"""The limits as the command line writes them, read into their values, and the refusal of a
command line that is wrong."""

import math

from pyct.config.budget import Budget
from pyct.config.plateau import Plateau
from pyct.config.solver_timeout import SolverTimeout


class UsageError(Exception):
    """The command line is wrong. Exit 2."""


def parse_budget(budget_text: str | None, flag: str = "budget") -> Budget:
    """The budget is a positive number of seconds. No flag is no deadline.

    ``flag`` names it in a refusal, so a sweep's total budget is refused in the budget's words.
    """
    if budget_text is None:
        return Budget()
    return Budget(seconds=_positive_seconds(budget_text, flag))


def parse_plateau(plateau_text: str | None) -> Plateau:
    """The plateau is a whole number of inputs above zero. No flag is no plateau stop.

    ``int()`` decides what a whole number is: digits with an optional sign.
    ``1.0`` and ``1e2`` are refused like ``2.5``, so the flag never needs a
    float parse.
    """
    if plateau_text is None:
        return Plateau()
    refusal = f"plateau must be a whole number above zero, got {plateau_text!r}"
    try:
        inputs = int(plateau_text)
    except ValueError as error:
        raise UsageError(refusal) from error
    if inputs <= 0:
        raise UsageError(refusal)
    return Plateau(inputs=inputs)


def parse_solver_timeout(solver_timeout_text: str | None) -> SolverTimeout:
    """The seconds each solve may take, a positive number. No flag is the default limit.

    Checked as the budget is, finite and above zero, so no value turns the
    limit off.
    """
    if solver_timeout_text is None:
        return SolverTimeout()
    return SolverTimeout(seconds=_positive_seconds(solver_timeout_text, "solver timeout"))


def _positive_seconds(text: str, flag: str) -> float:
    """``text`` as a finite number of seconds above zero. ``flag`` names it in a refusal.

    The budget and the solver timeout share this one rule. ``inf`` passes
    ``> 0``, so ``isfinite`` is what refuses it along with ``nan``.
    """
    try:
        seconds = float(text)
    except ValueError as error:
        raise UsageError(f"{flag} must be a number of seconds, got {text!r}") from error
    if not (math.isfinite(seconds) and seconds > 0):
        raise UsageError(f"{flag} must be a finite number of seconds above zero, got {text!r}")
    return seconds

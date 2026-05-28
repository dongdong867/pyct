"""Unprotected ``int(c)`` witness — ValueError must surface, not be absorbed.

Calls ``int(c)`` with no try / except wrapper. When the engine
generates a non-digit char, the underlying ``int`` raises
``ValueError`` and that exception must surface to the iteration
boundary exactly as Python would — neither caught silently by the
``ConcolicInt.__new__`` dispatch nor absorbed into a false-branch
constraint.

Anchors the ``non-digit-int-error-surfaces`` AC.
"""


def parse_digit(c: str) -> str:
    n = int(c)
    if n == 0:
        return "zero"
    return "nonzero"

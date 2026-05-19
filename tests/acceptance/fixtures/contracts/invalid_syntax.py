"""Fixture: predicate with invalid syntax — import must fail loudly.

Importing this module must raise ``PyCTContractSyntaxError`` at
decoration time (i.e., at module load). The acceptance test imports
this module *inside* the test body and asserts the failure.
"""

from pyct.contracts import pre


@pre("x >>")
def broken(x: int) -> int:
    return x

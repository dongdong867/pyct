"""Basic native-contract fixtures for end-to-end acceptance.

Each fixture is decorated with the public ``@pre`` / ``@post`` surface
from ``pyct.contracts`` so the engine's discover-and-filter pipeline is
exercised through the same path a user would write.
"""

from pyct.contracts import post, pre

MIN_VAL = 0


@pre("x > 0")
def requires_positive(x: int) -> int:
    if x > 100:
        return 2
    return 1


@pre("z > 0")
def requires_unknown_name(x: int) -> int:
    """Predicate refers to ``z`` which is not in the signature.

    Triggers the engine's NameError soft-fail path at eval time.
    """
    if x > 0:
        return 1
    return 0


@pre("x > MIN_VAL")
def requires_module_global(x: int) -> int:
    """Predicate refers to ``MIN_VAL`` from this module's __globals__."""
    if x > 100:
        return 2
    return 1


@pre("x.foo()")
def requires_attribute_call(x: int) -> int:
    """Predicate raises AttributeError when ``x`` is an int."""
    if x > 0:
        return 1
    return 0


@post("__return__ > 0")
def double(x: int) -> int:
    """Carries a postcondition; engine just discovers it (no oracle yet)."""
    return x * 2

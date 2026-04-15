"""Branches driven by bool() — witness for ConcolicInt.__bool__ branch registration.

The ``falsy`` arm is only reachable if ``bool(x)`` fires
``ConcolicInt.__bool__``, which registers a ``x != 0`` branch with the
engine's path tracker. Without that hook, the engine never sees a
branch point and can't synthesize ``x = 0``.
"""


def truthiness(x: int) -> str:
    if bool(x):
        return "truthy"
    return "falsy"

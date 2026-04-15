"""Bounded loop target — guard branches let the engine find n >= 1.

``range(n)`` uses the iterator protocol, which does not fire
ConcolicBool branches. The explicit ``if n < 1`` guard gives the
engine something to flip so the solver can synthesize an input that
enters the loop body.
"""


def power_of_two(n: int) -> int:
    if n < 1:
        return 1
    result = 1
    for _ in range(n):
        result *= 2
    return result

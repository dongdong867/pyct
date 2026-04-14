"""Bounded loop target — symbolic iteration count via range(n)."""


def power_of_two(n: int) -> int:
    result = 1
    for _ in range(n):
        result *= 2
    return result

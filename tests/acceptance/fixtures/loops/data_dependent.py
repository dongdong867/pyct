"""Data-dependent loop target — exit condition is symbolic."""


def countdown(n: int) -> int:
    steps = 0
    while n > 0:
        n -= 1
        steps += 1
    return steps

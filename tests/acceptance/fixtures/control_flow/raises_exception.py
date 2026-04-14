"""Target that raises a runtime error — engine must capture, not crash."""


def guarded(n: int) -> int:
    if n < 0:
        raise ValueError("n must be non-negative")
    return n * 2

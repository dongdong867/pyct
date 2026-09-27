def shift(n: int) -> object:
    # float has no `<<`, and neither has a tracked int beside a float
    return 0.5 << n


def power(n: int) -> float:
    # past the largest double, Python's own `**` raises OverflowError
    return 10.0**n

def count(x: float) -> int:
    n = 0
    if x < 1e-05:
        n += 1
    if x != 2.0:
        n += 1
    return n

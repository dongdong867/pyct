def count(x: float, y: float) -> int:
    n = 0
    if x != x:
        n += 1
    if y > 0.0:
        n += 2
    return n

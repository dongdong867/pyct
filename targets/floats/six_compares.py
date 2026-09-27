def count(x: float) -> int:
    n = 0
    if x < 1.0:
        n += 1
    if x <= 2.0:
        n += 1
    if x > 3.0:
        n += 1
    if x >= 4.0:
        n += 1
    if x == 5.0:
        n += 1
    if x != 6.0:
        n += 1
    if 2.5 < x:
        n += 1
    return n

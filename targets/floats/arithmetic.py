def count(x: float, y: float) -> int:
    n = 0
    if (x + 1.5) * 2.0 - 3.0 > 10.0:
        n += 1
    if abs(x) > 5.0:
        n += 1
    if -x < -3.0:
        n += 1
    if 10.0 - x > y:
        n += 1
    return n

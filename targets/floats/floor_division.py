def split(x: float, y: float) -> int:
    count = 0
    if x // 2.5 == 3.0:
        count += 1
    if x % 2.5 == 1.0:
        count += 1
    if x % -2.0 == -0.5:
        count += 1
    q, r = divmod(x, y)
    if q == 4.0:
        count += 1
    return count

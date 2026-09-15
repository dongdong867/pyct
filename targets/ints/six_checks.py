def count(x: int) -> int:
    n = 0
    if x < 1:
        n += 1
    if x <= 2:
        n += 1
    if x > 3:
        n += 1
    if x >= 4:
        n += 1
    if x == 5:
        n += 1
    if x != 6:
        n += 1
    return n

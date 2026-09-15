def mark(x: int, y: int) -> int:
    n = 0
    if x < 10:
        n += 1
    if y < 10:
        n += 1
    return n

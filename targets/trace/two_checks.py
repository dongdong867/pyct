def bucket(x: int) -> int:
    n = 0
    if x < 10:
        n += 1
    if x < 100:
        n += 1
    return n

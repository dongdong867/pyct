def place(x: int) -> int:
    n = 0
    if abs(x) > 5:
        n += 1
    if -x < -3:
        n += 1
    return n

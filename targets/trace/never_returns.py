def spin(x: int) -> int:
    n = 0
    while True:
        n ^= 1 << x
    return n

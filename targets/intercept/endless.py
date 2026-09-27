def conv(x: int) -> int:
    # recursion without end, through Python's own `int` on every level
    y = int(x)
    return conv(y)

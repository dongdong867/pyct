def cut(x: int) -> int:
    if x < 6:
        y = (0, 1, 2, 3, 4)[x]
        if x < 5:
            return y
        return 1
    return 2

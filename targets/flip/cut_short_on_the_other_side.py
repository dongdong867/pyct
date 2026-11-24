def cut(x: int) -> int:
    if x < 6:
        [0, 1, 2, 3, 4][x] = x
        if x < 5:
            return x
        return 1
    return 2

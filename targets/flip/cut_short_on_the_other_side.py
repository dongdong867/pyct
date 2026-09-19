def cut(x: int) -> float:
    if x < 6:
        y = 1 / (x - 5)
        if x < 5:
            return y
        return 1
    return 2

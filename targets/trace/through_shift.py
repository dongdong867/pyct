def size(x: int) -> str:
    y = x >> abs(x)
    if y < 10:
        return "small"
    return "big"

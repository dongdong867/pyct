def size(x: int) -> str:
    y = x >> 1
    if y < 10:
        return "small"
    return "big"

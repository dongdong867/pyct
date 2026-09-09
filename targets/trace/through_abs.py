def size(x: int) -> str:
    y = abs(x)
    if y < 10:
        return "small"
    return "big"

def big(x: int) -> str:
    c = x >> (x - x)
    if c > 10:
        return "big"
    return "small"

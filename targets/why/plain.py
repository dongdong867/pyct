def big(x: int) -> str:
    c = x ^ 0
    if c > 10:
        return "big"
    return "small"

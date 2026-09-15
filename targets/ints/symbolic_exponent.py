def grow(x: int) -> str:
    if 2**x > 8:
        return "big"
    return "small"

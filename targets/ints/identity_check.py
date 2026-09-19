def small(x: int) -> str:
    y = round(+x)
    if y < 10:
        return "small"
    return "big"

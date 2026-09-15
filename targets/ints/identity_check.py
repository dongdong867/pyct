def small(x: int) -> str:
    y = round(int(+x))
    if y < 10:
        return "small"
    return "big"

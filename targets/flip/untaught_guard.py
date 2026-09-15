def route(x: int) -> str:
    if x >> 1:
        if x < 20:
            return "teen"
        return "big"
    if x < 10:
        return "small"
    return "never"

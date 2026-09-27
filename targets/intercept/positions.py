def place(x: int) -> str:
    b = x > 5
    seen = []
    seen.append(x)
    if b is True:
        return "big"
    if x in {1,
             5}:
        return "picked"
    return "other"

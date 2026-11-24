def left(x: int) -> str:
    c = x >> (x - x)
    if x == c:
        return "same"
    return "other"

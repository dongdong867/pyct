def left(x: int) -> str:
    c = x ^ 0
    if x == c:
        return "same"
    return "other"

def explode(x: int) -> int:
    if x < 10:
        raise ValueError("too small")
    return x

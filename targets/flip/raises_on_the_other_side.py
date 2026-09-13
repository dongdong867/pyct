def guard(x: int) -> int:
    if x < 10:
        return x
    raise ValueError("out of range")

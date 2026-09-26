def pick(x: int, y: int) -> int:
    if not x > 3:
        x = 3
    a = 1 if y > 3 else 2
    return x + a

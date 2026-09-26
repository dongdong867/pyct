def combine(x: int, y: int) -> int:
    seen = 0
    if (x > 0) & (y > 0):
        seen += 1
    if (x > 0) | (y > 0):
        seen += 2
    if (x > 0) ^ (y > 0):
        seen += 4
    if (x > 0) == (y > 0):
        seen += 8
    return seen

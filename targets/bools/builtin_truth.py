def check(x: int, z: int) -> int:
    y = bool(x)
    seen = 0
    if y:
        seen += 1
    if any([x > 5, z > 5]):
        seen += 2
    return seen

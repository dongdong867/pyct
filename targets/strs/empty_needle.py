def past(s: str, n: int) -> int:
    hit = 0
    if s.find("", n) == -1:
        hit += 1
    if s.startswith("", n):
        hit += 1
    return hit

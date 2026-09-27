def hits(s: str, n: int) -> int:
    hit = 0
    if s.find("x", n) == 3:
        hit += 1
    if s.rfind("x", 0, n) == 1:
        hit += 1
    if s.count("a", n) == 2:
        hit += 1
    if s.startswith("b", n):
        hit += 1
    if s.endswith("c", 0, n):
        hit += 1
    if s.find("y", None, n) >= 0:
        hit += 1
    return hit

def walk_nothing(s: str) -> int:
    n = 0
    for c in s[:0]:
        n += 1
    return n

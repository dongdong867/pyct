def mark(s: str, t: str) -> int:
    hit = 0
    if s.replace("", "x", 1) == "xab":
        hit += 1
    if s.replace(t, "-", 1) == "a-c":
        hit += 1
    return hit

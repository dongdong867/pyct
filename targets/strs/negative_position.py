def tail(s: str, n: int) -> int:
    hit = 0
    if s[n] == "z":
        hit += 1
    if s[n:] == "yz":
        hit += 1
    return hit

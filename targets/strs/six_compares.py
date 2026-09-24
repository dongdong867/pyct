def count(s: str) -> int:
    n = 0
    if s < "b":
        n += 1
    if s <= "c":
        n += 1
    if s > "d":
        n += 1
    if s >= "e":
        n += 1
    if s == "f":
        n += 1
    if s != "g":
        n += 1
    return n

def count(s: str):
    n = 0
    for c in s:
        if c == "x":
            n += 1
    if n > 1:
        s = s.upper()
    return n

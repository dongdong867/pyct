def fill(s: str) -> str:
    t = s.format(x=1)
    if t == "1":
        return "one"
    return "other"

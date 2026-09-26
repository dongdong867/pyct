def shape(s: str) -> str:
    if s[0] == "a":
        return "first"
    if s[-1] == "z":
        return "last"
    if s[1:3] == "bc":
        return "middle"
    if s[2:] == "cd":
        return "tail"
    if s[:-1] == "xy":
        return "head"
    return "other"

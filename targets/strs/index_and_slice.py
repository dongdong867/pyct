def shape(s: str) -> str:
    try:
        if s[0] == "a":
            return "first"
    except IndexError:
        pass
    try:
        if s[-1] == "z":
            return "last"
    except IndexError:
        pass
    if s[1:3] == "bc":
        return "middle"
    if s[2:] == "cd":
        return "tail"
    if s[:-1] == "xy":
        return "head"
    return "other"

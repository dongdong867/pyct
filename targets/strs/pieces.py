def combine(s: str, t: str) -> str:
    if s + t == "ab":
        return "joined"
    if s.replace("a", "b") == "bbc":
        return "replaced"
    if s.removeprefix("x") == "yz":
        return "unprefixed"
    if s.removesuffix("y") == "xw":
        return "unsuffixed"
    return "other"

def band(x: int, flag: bool) -> str:
    if 0 < x in {1, 5, 9}:
        return "picked"
    if 1 == flag is True:
        return "flagged"
    return "other"

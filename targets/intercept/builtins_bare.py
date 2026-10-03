def code(c: str) -> str:
    if ord(c) == 97:
        return "a"
    return "other"


def sized(s: str) -> str:
    if len(s) > 3:
        return "long"
    return "short"


def character(n: int) -> str:
    if chr(n) == "A":
        return "A"
    return "other"

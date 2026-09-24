def match(s: str) -> str:
    if s == "\U00030000":
        return "found"
    return "other"

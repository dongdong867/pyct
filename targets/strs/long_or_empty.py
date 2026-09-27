def measure(s: str) -> str:
    if s[10:] != "":
        return "long"
    if s == "":
        return "empty"
    return "short"

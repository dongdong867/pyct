def look(s: str) -> str:
    y = "a" in s
    if y:
        return "a"
    if "b" not in s:
        return "no b"
    return "b"

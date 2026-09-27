def find_x(s: str) -> str:
    for c in s:
        if c == "x":
            return "found"
    return "none"

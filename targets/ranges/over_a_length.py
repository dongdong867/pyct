def find_x(s: str) -> str:
    for i in range(len(s)):
        if s[i] == "x":
            return "found"
    return "none"

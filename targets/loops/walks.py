def walk_both(s: str, t: str) -> str:
    if any(c == "@" for c in s):
        return "at"
    for a, b in zip(s, t):
        if a != b:
            return "differ"
    for i, c in enumerate(s):
        if c == "-":
            return "dash"
    return "plain"

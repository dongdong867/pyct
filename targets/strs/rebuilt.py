def rebuild(s: str) -> str:
    for i in range(len(s)):
        s = s[:i] + "x" + s[i + 1 :]
    if s == "abcdefghijklmnopqr":
        return "match"
    return "other"

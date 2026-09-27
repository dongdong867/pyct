def back(s: str, n: int) -> str:
    if s[n:0:-1] == "cb":
        return "back"
    return "other"

def head(s: str) -> str:
    if s.rsplit(",", 2000)[0] == "a":
        return "a"
    return "other"

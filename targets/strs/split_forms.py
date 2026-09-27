def read(s: str) -> str:
    if s.split(None, 1)[0] == "GET":
        return "get"
    if s.splitlines(True)[0] == "a\n":
        return "line"
    return "other"

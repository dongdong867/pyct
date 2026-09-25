def check(s: str, n: int) -> str:
    if s.find("x") < n:
        return "before"
    return "after"

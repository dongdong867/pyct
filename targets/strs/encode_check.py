def check(s: str) -> str:
    t = s.encode()
    if t == b"abc":
        return "abc"
    return "other"

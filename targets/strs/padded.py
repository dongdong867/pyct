def pad(s: str) -> str:
    for _ in range(5000):
        s = s + " "
    if s.startswith("ok"):
        return "ok"
    return "other"

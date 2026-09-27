LIMITS = {1: "one", 2: "two"}


def pick(s: str, n: int) -> str:
    if s in {"red", "green", "blue"}:
        return "color"
    if n in LIMITS:
        return "limit"
    if s not in set():
        return "anything"
    return "never"

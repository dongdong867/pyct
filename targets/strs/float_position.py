def cut(s: str, x: float) -> str:
    if s[int(x // 2)] == "z":
        return "z"
    return "other"

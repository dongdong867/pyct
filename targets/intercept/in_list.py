def later(s: str) -> str:
    y = s in ["a", "b"]
    if y:
        return "listed"
    return "not listed"

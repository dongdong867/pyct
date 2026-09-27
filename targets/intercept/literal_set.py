def route(x: int, s: str) -> str:
    if x in {1, 5, 9}:
        return "picked"
    if s in {"GET": 1, "POST": 2}:
        return "method"
    return "other"

def route(s: str, t: str) -> str:
    if s.startswith(("GET", "POST")):
        return "http"
    if s.endswith((".py", t)):
        return "source"
    return "other"

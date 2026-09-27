def key_of(s: str) -> str:
    key = s[: s.find("=")]
    if key == "port":
        return "port"
    return "other"

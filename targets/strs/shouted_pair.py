def pair(s: str) -> str:
    if s.upper().strip().split() == ["A", "B"]:
        return "pair"
    return "other"

def high(s: str) -> str:
    for c in s:
        if ord(c) > 100:
            return "high"
    return "low"


def measured(s: str) -> str:
    seen = 0
    for c in s:
        seen += 1
        if len(s) > 3:
            return "long"
    if len(s) == 2:
        return "two"
    return "other"

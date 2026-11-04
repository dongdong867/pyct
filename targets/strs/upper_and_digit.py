def both(s: str) -> int:
    for c in s:
        if c.isupper() and c.isdigit():
            return 1
    return 0

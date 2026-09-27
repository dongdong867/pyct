def code_at(s: str, n: int) -> int:
    if len(s) > 2 and ord(s[n]) == 122:
        return 1
    return 0

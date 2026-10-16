def pick(s: str):
    out = [
        c.upper()
        for c in s
        if c == "q"
    ]
    return out

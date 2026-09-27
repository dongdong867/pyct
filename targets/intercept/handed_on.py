def pair(s: str, t: str) -> str:
    a, b = map(len, [s, t])
    if a + b > 5:
        return "long pair"
    size = len
    if size(s) > 3:
        return "long s"
    return "short"

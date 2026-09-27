def check(s: str, n: int) -> int:
    k = 0
    if s.upper() == "A":
        k += 1
    if s.find("a") < n:
        k += 1
    return k

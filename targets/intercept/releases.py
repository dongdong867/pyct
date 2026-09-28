def f(x: int, s: str) -> str:
    if (x > 0) is True:
        return "positive"
    if s in "abc":
        return "listed"
    return "other"


def g(s: str) -> int:
    return int(s)


def sized(s: str) -> str:
    if len(s) == 3:
        return "three"
    return "other"

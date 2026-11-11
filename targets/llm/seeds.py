from targets.llm.helpers import sign


def f(x: int):
    if x == 1234:
        return 1
    if x > 5:
        return sign(x) + 2
    return sign(x)

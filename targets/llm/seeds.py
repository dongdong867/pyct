from targets.llm.helpers import sign


def f(x: int) -> int:
    if x == 1234:
        return 1
    return sign(x)

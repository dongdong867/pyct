def inner(x: int):
    yield 1
    yield 2


def delegating(x: int):
    yield from inner(x)
    yield 3


def via_yield_from(x: int) -> int:
    for v in delegating(x):
        return v
    return 0

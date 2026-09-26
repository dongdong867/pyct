"""A target that calls a helper defined beside it in the same file."""


def double(x: int) -> int:
    if x > 100:
        return x
    return x * 2


def route(x: int) -> str:
    y = double(x)
    if y > 10:
        return "big"
    return "small"

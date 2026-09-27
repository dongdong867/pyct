def numbers(x: int):
    yield x
    y = x + 1
    yield y


def first(x: int) -> int:
    # asks for one value and stops: the generator stays at its first yield
    return next(numbers(x))

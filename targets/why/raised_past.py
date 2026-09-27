def gen(x: int):
    yield 1
    y = {}["k"]
    yield y


def raised_past(x: int) -> object:
    try:
        return list(gen(x))
    except KeyError:
        return []

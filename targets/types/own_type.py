def type(value: object) -> object:
    return str


def f(x: int) -> str:
    if type(x) is str:
        return "own"
    return "python"

import functools


@functools.singledispatch
def kind(value: object) -> str:
    return "object"


@kind.register
def _(value: int) -> str:
    return "int"


@kind.register
def _(value: bool) -> str:
    return "bool"


@kind.register
def _(value: float) -> str:
    return "float"


@kind.register
def _(value: str) -> str:
    return "str"


@kind.register
def _(value: list) -> str:
    return "list"


def f(flag: bool, x: int, r: float, s: str, xs: list[int]) -> str:
    kinds = [kind(flag), kind(x > 0), kind(x), kind(r), kind(s), kind(xs)]
    if kinds == ["bool", "bool", "int", "float", "str", "list"]:
        return "python"
    return "other"

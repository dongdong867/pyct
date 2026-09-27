def kind(value: object) -> str:
    match value:
        case bool():
            return "bool"
        case int():
            return "int"
        case float():
            return "float"
        case str():
            return "str"
        case list():
            return "list"
        case _:
            return "other"


def f(flag: bool, x: int, r: float, s: str, xs: list[int]) -> str:
    kinds = [kind(flag), kind(x > 0), kind(x), kind(r), kind(s), kind(xs)]
    if kinds == ["bool", "bool", "int", "float", "str", "list"]:
        return "python"
    return "other"

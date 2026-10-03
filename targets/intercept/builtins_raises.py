import builtins


def sized(n: int) -> str:
    if builtins.len(n) > 3:
        return "long"
    return "short"


def g(x: int) -> str:
    return builtins.chr(x)

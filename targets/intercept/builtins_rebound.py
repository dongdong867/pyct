import builtins as bi


def unused() -> None:
    bi = None


def check(s: str) -> str:
    if bi.len(s) > 3:
        return "long"
    return "short"

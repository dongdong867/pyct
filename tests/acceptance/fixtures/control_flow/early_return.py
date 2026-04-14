"""Multiple return paths target — tests early-return semantics (3 distinct exits)."""


def safe_divide(a: int, b: int) -> float:
    if b == 0:
        return 0.0
    if a == 0:
        return 0.0
    return a / b

"""Missed lines no guess helps: a function nothing calls, a condition no input can take, and one
the solver can still reach, for the guess-inputs-when-stuck story."""


def helper(y: int) -> int:
    return y + 1


def skipped(x: int) -> str:
    if x != x:
        return "never"
    c = x >> (x - x)
    if x == c:
        return "same"
    return "other"

# Each function's seed passes equal values to the cache, so its path ends in the cache's key
# compares; flipping one gives a value whose hash differs, the compare never runs, and the input
# leaves the plan
from targets.flip.cached_number import number, strict_number


def curve(m: int, a: int, b: int, c: int, d: int, e: int, f: int) -> int:
    if m == 0:
        return 0
    return len([number(value) for value in (a, b, c, d, e, f)])


def numbers(a: int, b: int, c: int, d: int, e: int) -> int:
    return len([number(value) for value in (a, b, c, d, e)])


def apart(m: int, a: int, b: int) -> str:
    if m == 0:
        return "no modulus"
    if m == 1:
        return "one"
    if number(a) is number(b):
        return "same"
    return "apart"


def tail(m: int, a: int, b: int, x: int, y: int) -> str:
    if m == 0:
        return "no modulus"
    if m == 1:
        return "one"
    first, second = number(a), number(b)
    return "same" if first is second else ("a" if x < 5 else "b") + ("c" if y < 5 else "d")


def strict(m: int, a: int, b: int, c: int) -> int:
    if m == 0:
        return 0
    return len([strict_number(value) for value in (a, b, c)])

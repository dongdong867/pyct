"""Conditions that record no fork, each on a value a loop changed, for the
guess-inputs-when-stuck story."""


def counts(s: str) -> str:
    t = 0
    for c in s:
        if c == "z":
            t += 1
    if t > 25:
        return "many"
    return "few"


def two(s: str) -> str:
    t = 0
    for c in s:
        if c == "z":
            t += 1
    if t > 25:
        return "many"
    u = 0
    for d in s:
        if d == "y":
            u += 1
    if u > 25:
        return "lots"
    return "few"

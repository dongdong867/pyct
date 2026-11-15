"""Loops whose values the conditions after them read with no fork, for the
ask-for-a-stuck-loop-s-summary story."""


def tallies(s: str) -> str:
    ups = 0
    downs = 0
    for c in s:
        if c == "u":
            ups += 1
        elif c == "d":
            downs += 1
    if ups > 20:
        return "many ups"
    if downs > 20:
        return "many downs"
    return "few"


def stops(s: str) -> str:
    t = 0
    for c in s:
        if c == "!":
            return "stopped"
        if c == "z":
            t += 1
    if t > 25:
        return "many"
    return "few"


def vowels(s: str) -> str:
    kinds = {"a", "e", "i", "o", "u"}
    n = 0
    for c in s:
        if c in kinds:
            n += 1
    if n > 20:
        return "many"
    return "few"

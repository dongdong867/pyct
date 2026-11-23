"""Loops whose values the conditions after them read with no fork, for the summaries stories,
from ask-for-a-stuck-loop-s-summary through label-the-inputs-a-summary-gave."""


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


def few_z(s: str) -> str:
    t = 0
    for c in s:
        if c == "z":
            t += 1
    if t > 3:
        return "many"
    return "few"


def few_while(s: str) -> str:
    t = 0
    i = 0
    while i < len(s):
        if s[i] == "z":
            t += 1
        i += 1
    if t > 3:
        return "many"
    return "few"


def few_counted(s: str) -> str:
    t = sum(1 for c in s if c == "z")
    if t > 3:
        return "many"
    return "few"


def few_tallies(s: str) -> str:
    ups = 0
    downs = 0
    for c in s:
        if c == "u":
            ups += 1
        elif c == "d":
            downs += 1
    if ups > 3:
        return "many ups"
    if downs > 3:
        return "many downs"
    return "few"


def few_stops(s: str) -> str:
    t = 0
    for c in s:
        if c == "!":
            return "stopped"
        if c == "z":
            t += 1
    if t > 3:
        return "many"
    return "few"


def capped(s: str) -> str:
    t = 0
    for c in s:
        if c == "z" and t < 5:
            t += 1
    if t > 5:
        return "never"
    if t == 4:
        return "four"
    return "few"


def guarded(s: str) -> str:
    t = 0
    try:
        for c in s:
            if c == "#":
                raise ValueError(c)
            if c == "z":
                t += 1
    except ValueError:
        if s.startswith("#"):
            return "starts with #"
        if t > 3:
            return "many before #"
        return "holds #"
    if t > 3:
        return "many"
    return "few"


def encoded_z(s: str) -> str:
    t = 0
    for b in s.encode():
        if b == 122:
            t += 1
    if t > 3:
        if s.endswith("!"):
            return "many and loud"
        return "many"
    return "few"

"""A tracked str repeated a plain number of times: followed up to the bound, plain for a count
of zero or less, a downgrade past the bound or for a tracked count, and Python's error for a
count Python refuses."""


def twice(s: str):
    if s * 2 == "abab":
        return 1
    return 0


def on_the_left(s: str):
    t = 3 * s
    if t.startswith("xyx"):
        return 1
    return 0


def by_a_bool(s: str):
    if s * True == "a":
        return 1
    return 0


def in_place(s: str):
    s *= 2
    if len(s) == 6:
        return 1
    return 0


def nothing(s: str):
    if s * 0 == "" and s * -2 == "":
        return 1
    return 0


def at_the_bound(s: str):
    if s * 10 == "ab" * 10:
        return 1
    return 0


def tracked_count(s: str, n: int):
    if s * n == "abab":
        return 1
    return 0


def by_a_float(s: str):
    return s * 2.0


def too_many(s: str):
    return s * 2**64

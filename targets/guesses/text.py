"""Conditions whose asks run out of a short solver limit, for the guess-inputs-when-stuck story."""


def exponent(s: str) -> int:
    if float(s) == 1e-30:
        return 1
    return 0


def exponents(s: str, t: str) -> int:
    if float(s) == 1e-30:
        return 1
    if float(t) == 1e-20:
        return 2
    return 0

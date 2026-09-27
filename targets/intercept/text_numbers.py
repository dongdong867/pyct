import math


def thousand(s: str) -> str:
    if int(s) == 1000:
        return "thousand"
    return "other"


def with_a_base(s: str) -> str:
    if int(s, 16) == 255:
        return "ff"
    return "other"


def twelve(s: str) -> str:
    if int(s) == 12:
        return "twelve"
    return "other"


def read_as_float(s: str) -> str:
    if math.isnan(float(s)):
        return "nan"
    if float(s) == 100000.0:
        return "hundred thousand"
    return "other"


def not_itself(s: str) -> str:
    if float(s) != float(s):
        return "nan"
    return "a number"

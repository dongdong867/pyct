"""A tracked int searched among floats, which Python compares on the element's left."""

from enum import Enum


class Ratio(float, Enum):
    HALF = 0.5
    TWO = 2.0


def floats(x: int) -> str:
    if x in (0.5, 2.0):
        return "known"
    return "unknown"


def ratios(x: int) -> str:
    if x in (Ratio.HALF, Ratio.TWO):
        return "known"
    return "unknown"

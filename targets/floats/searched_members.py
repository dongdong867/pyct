"""A tracked float searched among float subclass values, which Python compares on the element's
left."""

from enum import Enum


class Ratio(float, Enum):
    HALF = 0.5
    FULL = 1.0


def ratios(f: float) -> str:
    if f in (Ratio.HALF, Ratio.FULL):
        return "known"
    return "unknown"

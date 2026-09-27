import math
from math import sqrt


def root(n: int) -> int:
    if math.sqrt(n) > 3.0:
        return 1
    return 0


def bare_root(n: int) -> int:
    if sqrt(n) > 3.0:
        return 1
    return 0

import math


def round_off(x: float, n: int) -> int:
    count = 0
    if math.floor(x) == 3:
        count += 1
    if math.ceil(x) == 3:
        count += 1
    if math.trunc(x) == -2:
        count += 1
    if round(x) == 4:
        count += 1
    if math.floor(x) < n:
        count += 1
    return count

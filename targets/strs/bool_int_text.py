import math


def counted(x: int) -> int:
    b = x > 0
    found = 0
    if str(+b) == "1":
        found += 1
    if str(math.trunc(b)) == "1":
        found += 2
    if str(round(b)) == "1":
        found += 4
    if f"{b.real}" == "1":
        found += 8
    return found

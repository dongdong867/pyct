import math


def read(x: float) -> int:
    count = 0
    if math.sqrt(x) > 2.0:
        count += 1
    if math.fabs(x) > 1.0:
        count += 1
    if math.copysign(1.0, x) < 0.0:
        count += 1
    if math.isnan(x):
        count += 1
    if math.isinf(x):
        count += 1
    if math.isfinite(x):
        count += 1
    if math.isclose(x, 0.1):
        count += 1
    return count

def int_of_int(x: int) -> str:
    y = int(x)
    if y > 10:
        return "big"
    return "small"


def bool_where_tested(x: int) -> int:
    y = bool(x)
    z = bool(x > 5)
    seen = 0
    if y:
        seen += 1
    if z:
        seen += 2
    return seen


def int_of_text(s: str) -> str:
    n = int(s)
    if n > 100:
        return "big"
    return "small"


def int_through_map(s: str, t: str) -> str:
    a, b = map(int, [s, t])
    if a + b == 10:
        return "ten"
    return "other"


def int_of_bool(x: int) -> str:
    b = x > 0
    if int(b) + 1 == 2:
        return "positive"
    return "other"


def int_of_float(x: float) -> str:
    if int(x) == 3:
        return "three"
    return "other"


def float_of_int(n: int) -> str:
    if float(n) / 2 > 2.5:
        return "big"
    return "small"


def float_of_float(x: float) -> str:
    y = float(x)
    if y > 2.5:
        return "big"
    return "small"


def float_of_bool(x: int) -> str:
    if float(x > 0) * 2.5 > 1.0:
        return "positive"
    return "other"


def float_of_text(s: str) -> str:
    if float(s) > 2.5:
        return "big"
    return "small"


def aliased(x: int) -> str:
    conv = int
    if conv(x) > 3:
        return "big"
    return "small"

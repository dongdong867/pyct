def int_text(n: int) -> str:
    if str(n) == "-42":
        return "minus"
    if str(n).startswith("9"):
        return "nines"
    return "other"


def kept_text(s: str) -> int:
    t = str(s)
    u = f"{s}"
    found = 0
    if t == "a":
        found += 1
    if u == "b":
        found += 2
    return found


def bool_text(x: int) -> str:
    b = x > 0
    if str(b) == "False":
        return "not positive"
    return "positive"


def formatted_alone(n: int) -> int:
    found = 0
    if f"{n}" == "7":
        found += 1
    if format(n) == "8":
        found += 2
    if "{}".format(n) == "9":
        found += 4
    if "%s" % n == "10":
        found += 8
    return found


def mapped(x: int, y: int) -> str:
    a, b = map(str, [x, y])
    if a + b == "12":
        return "twelve"
    return "other"


def joined(n: int) -> str:
    if f"n={n}" == "n=7":
        return "seven"
    if n > 3:
        return "big"
    return "small"


def with_spec(n: int) -> str:
    if f"{n:05d}" == "00007":
        return "padded"
    return "other"

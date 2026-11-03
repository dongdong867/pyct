def hex_beside_a_number(x: int, y: int):
    s = "%x|%d" % (x, y)
    if x > 3:
        if s.startswith("a|"):
            return "hex"
        return "above"
    return "below"


def precision_beside_a_name(xs: list[float], name: str):
    s = "%.1f %s" % (xs[0], name)
    if xs[0] > 1.0:
        if s.startswith("2.5"):
            return "written"
        return "above"
    return "below"


def text_as_a_key(d, xs):
    x = xs[0]
    if x > 0.0:
        if d[str(x)] > 5:
            return "hit"
    return "miss"


def percent_as_a_key(d, xs):
    x = xs[0]
    if x > 0.0:
        if d["%.1f" % x] > 5:
            return "hit"
    return "miss"


def flag_read_again_and_again(ys, flags):
    for _ in range(40_000):
        ys[flags[0]]
    if ys[1] > 5:
        return "hit"
    return "miss"


def compare_as_an_index(ys, xs):
    ys[xs[0] > 0]
    if xs[0] == -5:
        return "hit"
    return "miss"


def int_of_a_char_as_an_index(ys, s):
    i = int(s[0])
    ys[i]
    if s == "1":
        return "hit"
    return "miss"


def difference_as_an_index(ys, y, flags):
    ys[y - flags[0]]
    if y == 5:
        return "hit"
    return "miss"


def repr_beside_a_number(s: str, y: int):
    t = "%r|%d" % (s, y)
    if t.endswith("|5"):
        return "hit"
    return "miss"


def ascii_beside_a_number(s: str, y: int):
    t = "%a|%d" % (s, y)
    if t.endswith("|5"):
        return "hit"
    return "miss"


def list_beside_a_number(xs, y: int):
    t = "%s|%d" % (xs, y)
    if t.startswith("[9"):
        return "hit"
    return "miss"


def dict_beside_a_number(d, y: int):
    t = "%s|%d" % (d, y)
    if t.startswith("{'k': 9"):
        return "hit"
    return "miss"


def hex_as_a_key(d, x: int, y: int):
    t = "%x|%d" % (x, y)
    if t in d:
        return "hit"
    return "miss"


def hex_matched_by_a_walk(d, x: int, y: int):
    t = "%x|%d" % (x, y)
    for k in d:
        if k == t:
            return "hit"
    return "miss"


def hex_that_ends(x: int, y: int):
    s = "%x|%d" % (x, y)
    if s.endswith("|5"):
        return "hit"
    return "miss"


def float_that_ends(x: float, y: int):
    s = "%.2f|%d" % (x, y)
    if x > 1.0 and s.endswith("|5"):
        return "hit"
    return "miss"


def item_that_ends(xs: list[float], y: int):
    s = "%.2f|%d" % (xs[0], y)
    if xs[0] > 1.0 and s.endswith("|5"):
        return "hit"
    return "miss"

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

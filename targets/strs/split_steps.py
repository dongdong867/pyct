"""Splits v2 has no one formula for: a string cut at a tracked position, an int's text, a
piece read at a tracked index, a tracked separator or limit. pyct builds each from find and
slice steps, one fork per step."""


def cut_count(version: str, i: int):
    parts = version[i:].split(",")
    if len(parts) == 3:
        return 1
    return 0


def by_a_separator(s: str, d: str):
    parts = s.split(d)
    if parts[0] == "ab":
        return 1
    if len(parts) == 3:
        return 2
    return 0


def by_a_limit(s: str, n: int):
    parts = s.split(",", n)
    if len(parts) == 3:
        return 1
    return 0


def int_text(n: int):
    parts = str(n).split("0")
    if len(parts) == 3:
        return 1
    return 0


def joined_text(s: str, n: int):
    parts = (s + str(n)).split(",")
    if len(parts) == 3:
        return 1
    return 0


def by_whitespace(s: str, i: int, n: int):
    parts = s[i:].split(None, n)
    if len(parts) == 2 and parts[1] == "x":
        return 1
    return len(parts)


def from_the_right(s: str, i: int, d: str, n: int):
    parts = s[i:].rsplit(d, n)
    return parts


def by_whitespace_from_the_right(s: str, i: int, n: int):
    parts = s[i:].rsplit(None, n)
    return parts


def counted_by_a_loop(version: str, i: int):
    n = 0
    for p in version[i:].split(","):
        n += 1
    if n == 3:
        return 1
    return 0


def piece_at_an_index(s: str, i: int):
    first = s.split(";")[i]
    a, b = first.split(",")
    return a


def long_cut(s: str, i: int):
    parts = s[i:].split(",")
    return len(parts)


def long_plain_cut(s: str):
    parts = s[0:].split(",")
    return len(parts)


def unpacked_cut(version: str, i: int):
    s, rest = version[i:].split(" ", 1)
    return s


def limit_of_text(s: str, t: str):
    return s.split(",", t)


def limit_of_a_float(s: str, i: int):
    return s[i:].split(",", 1.5)


def one_formula(s: str):
    if len(s[1:].split(",")) == 2:
        return 1
    if s.split(maxsplit=1)[0] == "GET":
        return 2
    if len(s.rsplit(",", 2)) == 3:
        return 3
    return 0


def three_words_from_the_right(s: str, i: int):
    parts = s[i:].rsplit()
    if len(parts) == 3:
        return 1
    return 0

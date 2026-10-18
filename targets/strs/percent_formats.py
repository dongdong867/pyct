"""`%` formatting with tracked operands: followed, downgraded, plain, and raising."""

GREETING = "Hi %s, %d new"
WRAP = "<%s>"


def page(title: str, body: str):
    html = "<h1>%s</h1>%s" % (title, body)
    if "<script>" in html:
        return "unsafe"
    return "safe"


def count(n: int):
    if "%d items" % n == "3 items":
        return 1
    return 0


def greet(name: str, n: int):
    text = GREETING
    text %= (name, n)
    if text == "Hi bob, 2 new":
        return 1
    return 0


def kept(s: str):
    if "%s-%d%%" % (s, 7) == "ab-7%":
        return 1
    return 0


def on_the_right(s: str):
    fmt = WRAP
    if fmt % s == "<a>":
        return 1
    return 0


def padded(s: str):
    text = "%5s" % (s,)
    if text == "    a":
        return 1
    return 0


def in_hex(n: int):
    text = "%x" % (n,)
    if text == "ff":
        return 1
    return 0


def quoted(s: str):
    text = "%r" % (s,)
    if text == "'a'":
        return 1
    return 0


def keyed(s: str):
    text = "%(k)s" % {"k": s}
    if text == "a":
        return 1
    return 0


def tracked_format(s: str):
    text = s % (1,)
    if text == "1":
        return 1
    return 0


class Remainder:
    def __mod__(self, other):
        return ("mod", other)


def plain_values(n: int):
    k, v, x = "port", 80, b"x"
    pair = "%s=%d" % (k, v)
    raw = b"%s" % (x,)
    own = Remainder() % (k, v)
    if n > 0:
        return pair, raw, own
    return pair


def plain_int_format(n: int):
    x, two = 5, 2
    x %= (two,)
    if n > 0:
        return x
    return 0


def not_a_number(s: str):
    return "%d" % (s,)


def too_few(s: str):
    return "%s %s" % (s,)

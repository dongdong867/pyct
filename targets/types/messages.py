PLAIN = 3
PLAIN_N = 2
# a plain value of each type an argument can have, which the argument's messages are compared with
PLAINS = {int: 3, bool: True, float: 2.5, str: "ab", list: [1], dict: {"k": 1}}


def shifted(v):
    try:
        v << 2.0
    except TypeError as error:
        return str(error)
    return None


def shift_check(x):
    try:
        x << 2.0
    except TypeError as error:
        if str(error) == shifted(PLAIN):
            return "same"
        return "differs"
    return "none"


def shift(x):
    return x << 2.0


def message(operation):
    try:
        operation()
    except (TypeError, AttributeError) as error:
        return f"{type(error).__name__}: {error}"
    return None


def number_messages(v):
    return [
        message(lambda: v << 2.0),
        message(lambda: 2.0 << v),
        message(lambda: "a" + v),
        message(lambda: v < "a"),
        message(lambda: len(v)),
        message(lambda: v[0]),
    ]


def other_messages(v):
    return [
        message(lambda: v - 3),
        message(lambda: 3 - v),
        message(lambda: -v),
        message(lambda: v < 3),
        message(lambda: v()),
        message(lambda: v.foo),
        message(lambda: "%d" % v),
        message(lambda: b"-".join([v])),
        message(lambda: {v: 1}),
    ]


def each_form(x):
    if number_messages(x) == number_messages(PLAINS[type(x)]):
        return "same"
    return "differs"


def compare_result(x):
    if number_messages(x > 0) == number_messages(PLAIN > 0):
        return "same"
    return "differs"


def each_other_form(x):
    if other_messages(x) == other_messages(PLAINS[type(x)]):
        return "same"
    return "differs"


def each_view(d):
    plain = PLAINS[dict]
    if (
        other_messages(d.keys()) == other_messages(plain.keys())
        and other_messages(d.values()) == other_messages(plain.values())
        and other_messages(d.items()) == other_messages(plain.items())
    ):
        return "same"
    return "differs"


def ranged(n):
    if other_messages(range(n)) == other_messages(range(PLAIN_N)):
        return "same"
    return "differs"

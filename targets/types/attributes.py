def set_new(x):
    try:
        x.foo = 1
    except AttributeError:
        return "refused"
    return "set"


def set_by_name(x):
    try:
        setattr(x, "foo", 1)
    except AttributeError:
        return "refused"
    return "set"


def only_set(x):
    x.foo = 1


def set_then_delete(x):
    try:
        x.foo = 1
    except AttributeError:
        pass
    del x.foo


def set_on_a_compare(x):
    flag = x > 0
    try:
        flag.foo = 1
    except AttributeError:
        return "refused"
    return "set"


def set_pyct_s_names(x):
    try:
        x.sink = None
    except AttributeError:
        pass
    try:
        x.expression = "y"
    except AttributeError:
        pass
    if x > 10:
        return "big"
    return "small"

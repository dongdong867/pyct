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


def set_pyct_s_names_on_a_sized(x):
    try:
        x.sink = None
    except AttributeError:
        pass
    try:
        x.expression = "y"
    except AttributeError:
        pass
    if len(x) > 3:
        return "big"
    return "small"


def set_on_computed(s, xs):
    t = s.upper()
    xs.append(0)
    try:
        t.foo = 1
    except AttributeError:
        pass
    else:
        return "str set"
    try:
        xs.foo = 1
    except AttributeError:
        pass
    else:
        return "list set"
    if len(xs) > 3:
        return "big"
    if t == "":
        return "empty"
    return "small"


def computed_untouched(s, xs):
    t = s.upper()
    xs.append(0)
    if len(xs) > 3:
        return "big"
    if t == "":
        return "empty"
    return "small"


def set_on_a_range(n):
    r = range(n)
    kept = []
    try:
        r.foo = 1
    except AttributeError as error:
        kept.append(str(error))
    try:
        del r.foo
    except AttributeError as error:
        kept.append(str(error))
    try:
        r.sink = None
    except AttributeError as error:
        kept.append(str(error))
    for _ in r:
        pass
    raise LookupError(kept)


def set_pyct_s_names_on_a_range(n):
    r = range(n)
    try:
        r.sink = None
    except AttributeError:
        pass
    try:
        r.held = range(9)
    except AttributeError:
        pass
    for _ in r:
        pass
    return "walked"


def set_on_views(d):
    kept = []
    for view in (d.keys(), d.values(), d.items()):
        try:
            view.foo = 1
        except AttributeError as error:
            kept.append(str(error))
        try:
            del view.foo
        except AttributeError as error:
            kept.append(str(error))
    raise LookupError(kept)


def set_pyct_s_names_on_a_view(d):
    v = d.keys()
    try:
        v._mapping = None
    except AttributeError:
        pass
    if "k" in v:
        return "held"
    return "missing"

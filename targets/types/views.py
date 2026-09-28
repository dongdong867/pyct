PLAIN = {"k": 1}
VIEWS = ("keys", "values", "items")


def refused(call):
    try:
        call()
    except Exception as error:
        return f"{type(error).__name__}: {error}"
    return None


def each_type(d):
    for name in VIEWS:
        view = getattr(d, name)()
        python = type(getattr(PLAIN, name)())
        if not (type(view) is python and view.__class__ is python and isinstance(view, python)):
            return "other"
    return "base"


def guarded(d):
    keys = d.keys()
    if type(keys) is type(PLAIN.keys()) and "a" in keys:
        return "found"
    return "missing"


def built(d):
    for name in VIEWS:
        view = getattr(d, name)()
        python = getattr(PLAIN, name)()
        if refused(lambda: type(view)({"k": 1})) != refused(lambda: type(python)({"k": 1})):
            return "differs"
    return "same"

METAS = {"US": 1, "FR": 33, "DE": 49}


def found(s):
    meta = METAS.get(s)
    if meta == 1:
        return "us"
    if meta == 33:
        return "fr"
    if meta == 49:
        return "de"
    return "none"


def guarded(s):
    try:
        meta = METAS[s]
    except KeyError:
        return "none"
    if meta == 1:
        return "us"
    if meta == 33:
        return "fr"
    return "de"


def defaulted(s):
    return METAS.get(s, 7)


def raised(s):
    return METAS[s]

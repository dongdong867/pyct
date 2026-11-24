from collections import defaultdict

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


LARGE = {f"k{n}": n for n in range(301)}


def past_limit(s):
    count = LARGE.get(s)
    if count == 300:
        return "last"
    return "other"


class Doubled(dict):
    def __getitem__(self, key):
        return dict.__getitem__(self, key) * 2


DOUBLED = Doubled(METAS)
COUNTS = defaultdict(int, METAS)


def plain_key(s):
    meta = METAS["FR"]
    if s == "x":
        return meta
    return 0


def plain_key_missing(s):
    if s:
        return METAS["XX"]
    return 0


def own_read(s):
    return DOUBLED[s]


def counted(s):
    return COUNTS[s]


def held(d, s):
    return d[s]

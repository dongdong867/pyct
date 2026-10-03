PLAIN = {"k": 1, "j": 2}


class dict_values:
    """A class of the module's own, which a call through its name reaches as written."""

    @staticmethod
    def isdisjoint(view, other):
        return "own"


def kept(n, d):
    own = dict_values.isdisjoint(d.values(), ())
    size = type(range(n)).__len__(range(3))
    plain = type(d.keys()).__len__(PLAIN.keys())
    if own == "own" and size == 3 and plain == 2:
        return "kept"
    return "changed"

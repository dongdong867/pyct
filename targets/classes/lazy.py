"""A module that gives a function by its own ``__getattr__``, on each read."""


def _made(x):
    if x > 0:
        return "positive"
    return "other"


def __getattr__(name):
    if name == "made":
        return _made
    raise AttributeError(name)

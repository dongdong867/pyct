import copy
import pickle


def dict_type(d: dict[str, int]) -> str:
    built = type(d)({"k": 1})
    copied = copy.copy(d)
    if (
        isinstance(d, dict)
        and type(d) is dict
        and d.__class__ is dict
        and type(built) is dict
        and built == {"k": 1}
        and type(type(d)()) is dict
        and copied.__class__ is dict
    ):
        return "base"
    return "other"


def dict_pickled(d: dict[str, int]) -> str:
    loaded = pickle.loads(pickle.dumps(d))
    if type(loaded) is dict and loaded == {"a": 1}:
        return "base"
    return "other"

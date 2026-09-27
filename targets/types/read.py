import copy
import pickle


class Named(int):
    pass


def each_type(n: int, r: float, s: str, b: bool, xs: list[int]) -> str:
    if (
        type(n) is int
        and type(r) is float
        and type(s) is str
        and type(b) is bool
        and type(xs) is list
    ):
        return "base"
    return "other"


def guarded(x: int) -> str:
    if type(x) is int and x > 3:
        return "big"
    return "small"


def bool_checks(flag: bool, x: int) -> str:
    if (
        isinstance(flag, bool)
        and isinstance(x > 0, bool)
        and isinstance(flag, (str, bool))
        and issubclass(type(flag), bool)
        and type(x > 0) is bool
    ):
        return "bool"
    return "other"


def class_and_name(n: int, s: str, flag: bool, xs: list[int]) -> str:
    if (
        n.__class__ is int
        and flag.__class__ is bool
        and xs.__class__ is list
        and type(n) == int
        and type(n) in (int, float)
        and type(s).__name__ == "str"
        and s.__class__.__name__ == "str"
    ):
        return "base"
    return "other"


def rebuilt(n: int, r: float, s: str, b: bool, xs: list[int]) -> str:
    ys = type(xs)([1])
    ys.append(2)
    if (
        type(n)(5) == 5
        and type(r)(1.5) == 1.5
        and type(s)("hi") == "hi"
        and type(b)(0) is False
        and ys == [1, 2]
    ):
        return "plain"
    return "other"


def built(x: int) -> str:
    made = type("C", (), {"k": 1})
    if made.__name__ == "C" and made.k == 1:
        return "built"
    return "other"


def other_answers(n: int, flag: bool) -> str:
    if (
        isinstance(n, bool) is False
        and (n.__class__ is bool) is False
        and (type(flag) is int) is False
        and isinstance(flag, str) is False
        and isinstance(n, int)
        and isinstance(flag, int)
        and type(True) is bool
        and type(Named(3)) is Named
    ):
        return "python"
    return "other"


def rebuilt_from_text(x: int) -> int:
    return type(x)("abc")


def two_argument_type(x: int) -> object:
    return type(x, 1)  # type: ignore[call-overload]


def checked_against_a_number(flag: bool) -> bool:
    return isinstance(flag, 5)  # type: ignore[arg-type]


def range_type(n: int) -> str:
    r = range(n)
    if (
        isinstance(r, range)
        and type(r) is range
        and r.__class__ is range
        and type(r).__name__ == "range"
        and type(r)(3) == range(3)
    ):
        return "base"
    return "other"


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

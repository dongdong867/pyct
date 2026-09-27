from measure import classes


def checks(flag: bool, x: int) -> str:
    if (
        classes.is_flag(flag)
        and classes.is_flag(x > 0)
        and not classes.is_flag(x)
        and classes.class_of(x) is int
        and classes.class_of(flag) is bool
    ):
        return "python"
    return "other"


def rebuilt(n: int, r: float, s: str, b: bool, xs: list[int]) -> str:
    if (
        classes.rebuild(n, 5) == 5
        and classes.rebuild(r, 1.5) == 1.5
        and classes.rebuild(s, "hi") == "hi"
        and classes.rebuild(b, 0) is False
        and classes.rebuild(xs, [1]) == [1]
    ):
        return "plain"
    return "other"


def rebuilt_from_text(x: int) -> object:
    return classes.rebuild(x, "abc")

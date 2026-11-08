class Box:
    def __init__(self, v: int) -> None:
        self.v = v

    def __bool__(self) -> bool:
        return bool(self.v)


class Cmp:
    def __init__(self, v: int) -> None:
        self.v = v

    def __bool__(self) -> bool:
        return self.v != 0


class Flag:
    def __init__(self, v: int) -> None:
        self.v = v

    def __bool__(self) -> bool:
        return self.v > 0


class Inner:
    def __init__(self, v: int) -> None:
        self.v = v

    def __bool__(self) -> bool:
        def check() -> bool:
            return self.v != 0

        return check()


class Picked:
    def __init__(self, v: int) -> None:
        self.v = v

    def __bool__(self) -> bool:
        pick = lambda: self.v != 0
        return pick()


class Spread:
    def __init__(self, v: int) -> None:
        self.v = v

    def __bool__(self) -> bool:
        return (
            self.v
            != 0)


def __bool__(v: int) -> bool:
    return v != 0


def f(x: int) -> str:
    if Box(x):
        return "yes"
    return "no"


def g(x: int) -> str:
    if Cmp(x):
        return "yes"
    return "no"


def h(x: int) -> str:
    if Flag(3) and x > 0:
        return "yes"
    return "no"


def inner(x: int) -> str:
    if Inner(x):
        return "yes"
    return "no"


def picked(x: int) -> str:
    if Picked(x):
        return "yes"
    return "no"


def k(x: int) -> str:
    ok = __bool__(x)
    if ok:
        return "yes"
    return "no"


def spread(x: int) -> str:
    if Spread(x):
        return "yes"
    return "no"

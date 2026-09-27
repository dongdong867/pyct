class One:
    def __bool__(self) -> bool:
        return 1


class Num:
    def __init__(self, v: int) -> None:
        self.v = v

    def __bool__(self) -> bool:
        return self.v


def p(x: int) -> str:
    if x > 0 and One():
        return "yes"
    return "no"


def q(x: int) -> str:
    if Num(x):
        return "yes"
    return "no"

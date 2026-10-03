"""Calls whose end a host program's tracer acts on, for the tests where a raise on the way out of
the deadline's block skips its exit."""


def returns(x: int) -> int:
    return x


def raises(x: int) -> int:
    raise ValueError("raised at once")


def loops(x: int) -> int:
    while True:
        pass

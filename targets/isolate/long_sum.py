"""One C call that never checks for signals, about 2 s on 3.12 and 1.3 s on 3.14 where it was
measured, for the tests where a Ctrl-C and the deadline's alarm both wait for it to return."""

TERMS = 300_000_000


def total(x: int) -> int:
    return sum(range(TERMS))


def total_then_finally(x: int) -> int:
    try:
        return sum(range(TERMS))
    finally:
        x = 1

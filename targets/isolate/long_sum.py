"""One C call that never checks for signals, about 0.7 s where it was measured, for the tests
where a Ctrl-C and the deadline's alarm both wait for it to return."""

TERMS = 100_000_000


def total(x: int) -> int:
    return sum(range(TERMS))


def total_then_finally(x: int) -> int:
    try:
        return sum(range(TERMS))
    finally:
        x = 1

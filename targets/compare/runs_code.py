"""Targets with lines that compile to no code a call runs: global, nonlocal, class level."""

COUNT = 0


def tally(x: int) -> int:
    """Count x in, through an inner function."""
    global COUNT
    step = 1

    def bump() -> None:
        nonlocal step
        step += x

    bump()
    COUNT += step
    return step


class Counter:
    """A counter that starts from n."""

    start = 0

    def __init__(self, n: int) -> None:
        self.count = n

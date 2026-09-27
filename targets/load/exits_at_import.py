"""A module that calls ``sys.exit(4)`` while it is imported."""

import sys

sys.exit(4)


def f(x: int) -> int:
    return x

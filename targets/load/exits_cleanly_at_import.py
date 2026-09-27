"""A module that calls ``sys.exit()`` while it is imported."""

import sys

sys.exit()


def f(x: int) -> int:
    return x

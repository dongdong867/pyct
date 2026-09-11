import sys


def leave(x: int) -> int:
    if x < 10:
        sys.exit(3)
    return x

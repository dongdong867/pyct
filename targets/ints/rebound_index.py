"""`index` imported from operator and bound another way too: the call stays as written."""

from operator import index


def kept(n: int):
    if index(n) > 10:
        return 1
    return 0


def rebind() -> None:
    global index
    index = int

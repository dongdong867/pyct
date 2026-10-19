"""`len` of a tracked range: Python's count, followed, from either end and on an empty range."""


def counted(n: int):
    if len(range(n)) == 5:
        return 1
    return 0


def stepped_down(a: int, b: int):
    if len(range(a, b, -3)) == 4:
        return 1
    return 0


def emptied(a: int):
    if len(range(a, 10, 2)) == 0:
        return 1
    return 0


def tracked_step(k: int):
    if len(range(0, 20, k)) == 3:
        return 1
    return 0


def too_long(n: int):
    return len(range(n, 2**64))


def called_directly(n: int):
    return range(n).__len__()

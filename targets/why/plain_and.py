LIMIT = 0


def guarded(x: int) -> int:
    if LIMIT > 0 and x > 0:
        return 1
    return 2

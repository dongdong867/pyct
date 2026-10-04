# The seed takes every check's true side and runs every line, so no flip covers a new line
def three_deep(x: int) -> int:
    size = 0
    if x > 0:
        size += 1
        if x > 10:
            size += 1
            if x > 20:
                size += 1
    return size


def implied_deepest(x: int) -> int:
    size = 0
    if x > 0:
        size += 1
        if x > 10:
            size += 1
            # x > 10 implies it, so its flip is unsat
            if x > 5:
                size += 1
    return size

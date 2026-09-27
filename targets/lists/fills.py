def walk(items):
    for x in items:
        pass


def walk_strs(items: list[str]):
    for x in items:
        pass


def walk_floats(items: list[float]):
    for x in items:
        if x > 1.5:
            return "big"
    return "small"

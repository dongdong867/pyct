def last(items):
    if items[len(items) - 1] > 5:
        return "big"
    return "small"


def all_but_last(items):
    rest = items[: len(items) - 1]
    if rest[0] > 5:
        return "big"
    return "small"


def named_length(items):
    n = len(items)
    if items[n - 1] > 5:
        return "big"
    return "small"

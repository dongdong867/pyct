def at_the_limit(items):
    if items[999_999] == 1:
        return "last"
    return "other"


def past_the_limit(items):
    if items[1_000_000] == 1:
        return "past"
    return "other"

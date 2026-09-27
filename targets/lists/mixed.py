def last_is_a(items):
    if items[-1] == "a":
        return "a"
    return "other"


def first_after_append(items):
    items.append(5)
    if items[0] > 3:
        return "big"
    return "small"

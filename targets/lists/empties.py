def check(items):
    if not items:
        return "empty"
    if items[-1] > 5:
        return "big"
    return "small"

def check(items):
    items.append(0)
    if len(items) > 3:
        return "long"
    if items:
        return "some"
    return "none"

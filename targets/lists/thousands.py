def gather(data, items):
    for x in data:
        if x > 0:
            items.append(x)
    if items[3] == 42:
        return "fourth"
    if items[-1] == 42:
        return "last"
    return "other"

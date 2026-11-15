def each(s, items):
    for x in items:
        if x > 0 and float(s) == 1e-30:
            return x
    return 0


def changing(items):
    for i in range(len(items)):
        if float(items[i]) == 1e-30:
            return i
    return -1

def count(items, limits):
    big = 0
    for x in items:
        if x > 10:
            big += 1
    for name, limit in limits.items():
        if limit < 0:
            return name
    return big

def check(items):
    if 7 in items:
        return "seven"
    if items == [1, 2]:
        return "pair"
    if items < [5]:
        return "below"
    return "other"

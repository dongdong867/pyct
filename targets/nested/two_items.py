def classify(items):
    if items[0] > 100:
        return "big"
    if items[1] < -50:
        return "small"
    if items[0] == items[1]:
        return "same"
    return "other"

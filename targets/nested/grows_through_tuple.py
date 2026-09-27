def grow(a, b):
    if len(a) != 1:
        raise ValueError("an earlier input changed the arguments")
    b[0].append(0)
    if a[0] > 5:
        return "big"
    return "small"

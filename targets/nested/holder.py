def grow(a, h):
    if len(a) != 1:
        raise ValueError("an earlier input changed the arguments")
    h.xs.append(0)
    if a[0] > 5:
        return "big"
    return "small"

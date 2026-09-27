def grow(a, h):
    # the caller's own list, grown through h, would end in the None an earlier input appended
    if a and a[-1] is None:
        raise ValueError("an earlier input changed the arguments")
    h.xs.append(None)
    if a and a[0] > 5:
        return "big"
    return "small"

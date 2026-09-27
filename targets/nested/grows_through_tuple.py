def grow(a, b):
    # an earlier input's append would still end a: the one None in a list of ints
    if a and a[-1] is None:
        raise ValueError("an earlier input changed the arguments")
    b[0].append(None)
    if a[0] is not None and a[0] > 5:
        return "big"
    return "small"

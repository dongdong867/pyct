def check(xs):
    # reading the list at 1 keeps it two long on every path, so an answer keeps what it holds
    if xs[1] is xs and xs[0] > 5:
        return "big"
    return "small"

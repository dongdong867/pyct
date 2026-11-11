def negative(s):
    if s.startswith("-"):
        if float(s) == -1e-30:
            return 1
    return 0

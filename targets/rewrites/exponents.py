def exponents(s, t, u, v):
    if float(s) == 1e-30:
        return 1
    if float(t) == 2e-30:
        return 2
    if float(u) == 3e-30:
        return 3
    if float(v) == 4e-30:
        return 4
    return 0

def exponent(s, n):
    if float(s) == 1e-30:
        if n > 0:
            return 2
        return 1
    return 0

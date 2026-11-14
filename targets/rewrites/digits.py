def big(s):
    if s.isdigit() and int(s) > 10**30:
        return 1
    return 0

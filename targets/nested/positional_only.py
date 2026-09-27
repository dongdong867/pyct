def check(value, /, strict=False):
    if value == "abc":
        return "match"
    return "strict" if strict else "loose"

def same(flag: bool, other: bool) -> str:
    if flag is other:
        return "same"
    if True is flag is other:
        return "never"
    return "differ"

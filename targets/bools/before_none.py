def check(flag: bool, other: bool) -> str:
    if True is flag is not None:
        return "true"
    if flag is other is not None:
        return "same"
    return "other"

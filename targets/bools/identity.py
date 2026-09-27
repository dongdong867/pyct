def check(flag: bool, x: int) -> str:
    if flag is True:
        return "true"
    if flag is not False:
        return "not false"
    if x is None:
        return "none"
    return "false"

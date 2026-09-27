def flip(flag: bool, x: int) -> str:
    if flag:
        return "on"
    if flag + x > 5:
        return "high"
    return "low"

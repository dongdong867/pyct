def split(x: int) -> str:
    q, r = divmod(x, 5)
    if r == 3:
        return "three"
    return "other"

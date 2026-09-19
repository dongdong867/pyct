def root(x: int) -> str:
    if x < 0:
        if x**2 == 9:
            return "minus three"
        return "negative"
    return "not negative"

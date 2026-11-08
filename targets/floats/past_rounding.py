def between(x: int) -> str:
    if x > 2.0**53 and x < 2.0**53 + 2:
        return "between"
    return "outside"

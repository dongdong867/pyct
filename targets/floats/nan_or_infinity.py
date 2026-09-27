def kind(x: float) -> str:
    if x != x:
        return "nan"
    if x > 1.7976931348623157e308:
        return "infinity"
    return "finite"

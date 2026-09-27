def tie(x: float) -> str:
    if x >= 2.5:
        if round(x) == 2:
            return "even"
        return "up"
    return "low"

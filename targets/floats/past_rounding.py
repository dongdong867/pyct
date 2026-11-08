def above(x: int) -> str:
    if x > 2.0**53:
        return "above"
    return "not above"

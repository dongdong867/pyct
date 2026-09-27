def both(x: int, y: int) -> str:
    if x > 0 and y > 0:
        return "both above"
    if x < -5 or y < -5:
        return "one far below"
    return "neither"

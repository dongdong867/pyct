def tally(x: int, y: int) -> str:
    if (x > 0) + (y > 0) == 2:
        return "both positive"
    if sum([x > 5, y > 5]) == 0:
        return "neither above five"
    return "some above five"

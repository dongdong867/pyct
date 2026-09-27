def deep(x: int, y: int) -> str:
    # nothing is ever unequal to itself
    if x != x:
        if y > 0:
            return "deep"
    return "shallow"

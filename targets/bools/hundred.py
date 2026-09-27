SMALL = set(range(100))
LARGE = set(range(101))


def within(n: int) -> str:
    if n in SMALL:
        return "small"
    if n in LARGE:
        return "large"
    return "neither"

def parse(x: int) -> object:
    try:
        n = int("5")
    except ValueError:
        return "bad"
    return n + x

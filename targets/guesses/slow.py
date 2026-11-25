"""A handler line, and a value that spins until the budget ends, for the guess-inputs-when-stuck
story."""


def slow(s: str) -> int:
    try:
        value = int(s, 16)
    except ValueError:
        return -1
    while value > 1000:
        pass
    return value

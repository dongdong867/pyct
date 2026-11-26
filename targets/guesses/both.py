"""A handler line and a line every input that gets there ends before, in one function, for the
guess-inputs-when-stuck story."""


def both(s: str, t: str) -> int:
    try:
        value = int(s, 16)
    except ValueError:
        return -1
    total = value + int(t, 16)
    return total

"""A line every input that gets there ends before, since pyct does not follow `int(s, 16)`, for the
guess-inputs-when-stuck story."""


def ended(s: str) -> int:
    value = int(s, 16)
    return value

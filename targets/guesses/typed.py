"""A handler line under an int parameter, for the guess-inputs-when-stuck story."""


def typed(x: int) -> int:
    try:
        value = bytes([x])
    except ValueError:
        return -1
    return len(value)

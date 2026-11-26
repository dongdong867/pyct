"""A fork only an input that raises into the handler reaches, for the guess-inputs-when-stuck
story."""


def later(s: str, n: int) -> int:
    try:
        value = int(s, 16)
    except ValueError:
        if n > 5:
            return 2
        return 1
    return value

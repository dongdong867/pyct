"""A handler line whose way passes `if n > 10:`, for the guess-inputs-when-stuck story."""


def deep(s: str, n: int) -> int:
    if n > 10:
        try:
            value = int(s, 16)
        except ValueError:
            return -1
        return value
    return 0

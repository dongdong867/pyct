"""A handler line, and a loop each longer input passes once more without a new line, so a run is
stuck again and again, for the guess-inputs-when-stuck story."""


def counted(s: str, n: int) -> int:
    for _ in range(n):
        pass
    try:
        value = int(s, 16)
    except ValueError:
        return -1
    return value

def deep(n: int) -> int:
    # one frame per step down to zero, so a large n passes Python's recursion limit
    if n <= 0:
        return 0
    return 1 + deep(n - 1)

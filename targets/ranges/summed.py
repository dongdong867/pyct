def total_of(n: int) -> str:
    total = sum(range(n))
    if total > 10:
        return "big"
    return "small"

def count_up(x: int) -> str:
    for _ in range(5000):
        x = x + 1
    if x > 5010:
        return "high"
    return "low"

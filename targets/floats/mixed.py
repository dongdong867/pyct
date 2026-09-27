def mix(n: int, x: float) -> int:
    count = 0
    if n + 0.5 > x:
        count += 1
    if n < 2.5:
        count += 1
    return count

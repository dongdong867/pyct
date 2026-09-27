def plain(n: int) -> int:
    rng = range
    total = 0
    for i in rng(n):
        total += i
    for j in range(3):
        total += j
    return total

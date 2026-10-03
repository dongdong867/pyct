def thrice(x: int) -> int:
    hits = 0
    for _ in range(3):
        if x > 5:
            hits += 1
    return hits

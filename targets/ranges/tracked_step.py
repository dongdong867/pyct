def every(k: int) -> int:
    count = 0
    for i in range(0, 10, k):
        count += 1
    return count

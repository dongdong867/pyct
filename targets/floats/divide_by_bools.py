def ratio(n: int, m: int) -> int:
    count = 0
    if n / True > 2.5:
        count += 1
    if n / (m > 3) > 2.5:
        count += 1
    return count

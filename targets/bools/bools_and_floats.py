def mix(f: float, flag: bool) -> int:
    count = 0
    if f + True > 2.5:
        count += 1
    if flag * 2.5 > f:
        count += 2
    return count

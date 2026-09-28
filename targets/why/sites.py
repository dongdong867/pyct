def sites(x: int) -> int:
    for i in range(3):
        c = x ^ i
    d = x ^ 1
    return c + d

# how many values of x the target tells apart, one fork each
VALUES = 60


def pick(x: int) -> int:
    for n in range(VALUES):
        if x == n:
            return n
    return -1

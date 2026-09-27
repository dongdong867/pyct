def or_join(x: int) -> str:
    if x != x or x + 1 == x:
        return "never"
    return "always"


def elif_chain(x: int) -> int:
    if x != x:
        c = 1
    elif x + 1 != x + 1:
        c = 2
    else:
        return 0
    return c


def loop_forever(x: int) -> int:
    while x == x:
        if x > 5:
            return 1
        # plain from here on, so the loop's test forks once
        x = 6
    return 0

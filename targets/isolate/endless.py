def spin(n: int, m: int) -> str:
    if m > 3:
        return "big"
    if n == 7:
        # n stays 7, so this loop never ends, and it forks on every pass
        while n > 0:
            pass
    return "small"


def outlast(n: int) -> str:
    while True:
        try:
            # forks on every pass, and catches the deadline's raise to go on
            while n > 0:
                pass
        except BaseException:
            pass

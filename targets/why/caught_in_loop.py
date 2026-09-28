TABLE = {"k": 1}


def caught_in_loop(x: int) -> int:
    total = 0
    for i in range(2):
        try:
            v = TABLE["z"]
            total += v
        except KeyError:
            continue
    return total + x

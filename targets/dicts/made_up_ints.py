def counted(d: dict[int, int]):
    if d:
        for k, v in d.items():
            if v > 10:
                return k
        return "some"
    return "none"


def counted_unannotated(d):
    if d:
        for k, v in d.items():
            if v > 10:
                return k
        return "some"
    return "none"


def skips(d: dict[int, int]):
    if 1 in d:
        return 0
    if len(d) > 1:
        return 1
    return 2


def tracked(n: int, d: dict[int, int]):
    if n in d:
        return 1
    return 0

def walk_twice(d: dict):
    n = 0
    for k in d:
        n += 1
    for k in d:
        if k == "zz":
            return -1
    return n


def walked_length(d: dict):
    for k in d:
        pass
    if len(d) > 0:
        return 1
    return 0


def walked_truth(d: dict):
    for k in d:
        pass
    if d:
        return 1
    return 0


def unproven(d: dict, e: dict):
    for k in d:
        pass
    for k in e:
        pass
    if len(d) - len(e) > 0:
        k = 1
    if len(d) // 2 > 0:
        k = 1
    if len(d) % 2 == 1:
        k = 1
    return 0

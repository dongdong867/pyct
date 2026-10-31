def row_by_position(row):
    if row[0] == 7:
        if row[1] > 2.5:
            if row[2]:
                return "all"
    return "not all"


def last_float(row):
    if row[-1] > 2.5:
        return "above"
    return "other"


def last_int(row):
    if row[-1] > 2.5:
        return "above"
    return "other"


def isinstance_guard(row):
    if isinstance(row[1], float):
        if row[1] > 2.5:
            return "above"
    return "other"


def added_to_ints(xs):
    ys = xs + [2.5]
    if ys[0] > 1.5:
        return "above"
    if ys[1] > 1.0:
        return "added"
    return "other"

def found(xs):
    if 2.5 in xs:
        return "found"
    return "not found"


def counted(xs):
    if xs.count(2.5) == 2:
        return "twice"
    return "other"


def indexed(xs):
    if xs.index(2.5) == 1:
        return "second"
    return "other"


def equals(xs):
    if xs == [2.5, True]:
        return "equal"
    return "other"


def total(xs):
    if sum(xs) == 4.0:
        return "four"
    return "other"


def lowest_highest(xs):
    if min(xs) > 2.5:
        return "all above"
    if max(xs) < -1.5:
        return "all below"
    return "other"


def first_sorted(xs):
    if sorted(xs)[0] > 2.5:
        return "above"
    return "other"


def sorted_mixed(xs):
    if sorted(xs)[0] > 2.5:
        return "above"
    return "other"


def after_append(xs):
    xs.append(2.5)
    if xs[0] > 1.5:
        return "above"
    return "other"


def after_append_argument(xs, f):
    xs.append(f)
    if xs[1] > 1.5:
        return "above"
    return "other"


def after_pop(xs):
    if xs.pop() > 2.5:
        return "above"
    return "other"


def after_set(xs):
    xs[0] = xs[0] + 1.0
    if xs[0] > 2.5:
        return "above"
    return "other"


def walked_back(xs):
    for x in reversed(xs):
        if x > 2.5:
            return "above"
    return "other"


def sliced(xs):
    if xs[1:][0] > 2.5:
        return "above"
    return "other"


def under_tracked_index(xs, i):
    if 0 <= i < len(xs):
        if xs[i] > 2.5:
            return "above"
    return "other"

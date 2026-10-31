def nan_item(xs):
    if xs[0] != xs[0]:
        return "nan"
    return "number"


def minus_zero_item(xs):
    if xs[0] == 0.0:
        return "zero"
    return "other"


def infinite_item(xs):
    if xs[0] == float("inf"):
        return "infinite"
    return "finite"


def same_list(xs):
    if xs == xs:
        return "same"
    return "other"


def searched_itself(xs):
    x = xs[0]
    if x in xs:
        return "found"
    return "not found"


def annotated_list(xs: list[float]):
    if xs:
        if xs[0] == 2.5:
            return "equal"
    return "other"


def annotated_flags(xs: list[bool]):
    if xs:
        if xs[0]:
            return "on"
    return "other"


def no_annotation(xs):
    if xs:
        if xs[0] == 2.5:
            return "equal"
    return "other"


def finite_answer(xs):
    if xs[0] > 0.0:
        return "above"
    return "other"


def freed_beside(xs, ys):
    if xs[0] != xs[0]:
        if ys[0] > 1.0:
            return "both"
    return "other"

def walk_of_reversed_rows(g, n):
    for row in reversed(g):
        pass
    if n == 7:
        return "hit"
    return "miss"


def walk_of_growing_rows(g, n):
    for row in reversed(g):
        row.append(0)
    if n == 7:
        return "hit"
    return "miss"


def walk_of_rows_given_floats(g, n):
    for row in reversed(g):
        row.append(0.5)
    if n == 7:
        return "hit"
    return "miss"


def walk_of_rows_given_rows(g, n):
    for row in reversed(g):
        row.append([0])
    if n == 7:
        return "hit"
    return "miss"

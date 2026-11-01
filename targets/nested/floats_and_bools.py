def ratio_and_flags(data):
    if data["ratio"] > 2.5:
        return "high"
    if data["flags"][0]:
        return "flagged"
    return "plain"


def flag_item(xs):
    if xs[0]:
        return "on"
    return "off"


def not_flag_item(xs):
    if not xs[0]:
        return "off"
    return "on"


def flag_value(d):
    if d["k"]:
        return "on"
    return "off"


def is_true_value(d):
    if d["k"] is True:
        return "on"
    return "off"


def two_flags(d):
    if d["a"] and d["b"]:
        return "both"
    return "not both"


def float_item_equal(xs):
    if xs[0] == 2.5:
        return "equal"
    return "other"


def float_item_above(xs):
    if xs[0] > 2.5:
        return "above"
    return "other"


def float_value_equal(d):
    if d["k"] == 2.5:
        return "equal"
    return "other"


def float_value_sum(d):
    if d["k"] + 0.5 == 2.5:
        return "equal"
    return "other"


def float_deep(d):
    if d["a"][0] == 2.5:
        return "equal"
    return "other"


def mixed_row(row):
    if row["age"] == 30 and row["name"] == "x":
        if row["score"] > 2.0:
            if row["ok"]:
                return "all"
    return "not all"


def grid_row(grid):
    for row in grid:
        if row[0] > 2.5:
            return "above"
    return "other"


# placed here so the lines above keep their numbers, which accepted-per-merge.jsonl records
import math  # noqa: E402


def last_row_flag(grid, other):
    if other > 5:
        return "other"
    row = grid[-1][0:]
    if row[0]:
        return "set"
    return "clear"


def picked_row_floor(grid, i):
    row = grid[i] + [1.5]
    if math.floor(row[0]) == 3:
        return "three"
    return "other"


def picked_row_nan(grid, i):
    row = grid[i] + [1.5]
    if row[0] != row[0]:
        return "nan"
    return "a number"


def picked_row_above(grid, i):
    if grid[i][0] > 3.0:
        return "hit"
    return "miss"


def picked_row_flag(grid, i):
    if grid[i][0]:
        return "on"
    return "off"


def picked_row_then_index(grid, i):
    if grid[i][0] > 3.0:
        if i == 0:
            return "first"
        return "hit"
    return "miss"


def cut_item_above(xs, i):
    rest = xs[i:]
    if rest[0] > 3.0:
        return "hit"
    return "miss"


def joined_item_above(ys, xs):
    zs = ys + xs
    if zs[1] > 3.0:
        return "hit"
    return "miss"

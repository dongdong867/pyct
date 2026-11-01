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


def sorted_row_above(grid, i):
    row = grid[i]
    row.sort()
    if row[0] > 3.0:
        return "hit"
    return "miss"


def sorted_row_equal(grid, i):
    row = grid[i]
    row.sort()
    if row[0] == 0.75:
        return "hit"
    return "miss"


def sorted_row_floor(grid, i):
    row = grid[i]
    row.sort()
    if math.floor(row[0]) == 3:
        return "hit"
    return "miss"


def sorted_row_is_true(grid, i):
    row = grid[i]
    row.sort()
    if row[0] is True:
        return "hit"
    return "miss"


def sorted_cut_equal(xs):
    rest = xs[1:]
    rest.sort()
    if rest[0] == 0.75:
        return "hit"
    return "miss"


def popped_and_sorted(xs):
    xs.pop()
    xs.sort()
    if xs[0] + 0.5 > 2.5:
        return "hit"
    return "miss"


def sorted_ints_row(grid, i):
    row = grid[i]
    row.sort()
    if row[0] == 5:
        return "hit"
    return "miss"


def cut_row_above(grid, i):
    row = grid[i:][0]
    if row[0] > 3.0:
        return "hit"
    return "miss"


def keyed_row_above(d, k):
    if d[k][0] > 3.0:
        return "hit"
    return "miss"


def joined_row_above(ys, grid):
    if (ys + grid)[1][0] > 3.0:
        return "hit"
    return "miss"


def picked_dict_above(rows, i):
    if rows[i]["x"] > 3.0:
        return "hit"
    return "miss"


def last_dict_above(rows):
    if rows[-1]["x"] > 3.0:
        return "hit"
    return "miss"


def long_appended_float(xs):
    for _ in range(600):
        xs.append(0.5)
    if xs[0] > 3.0:
        return "hit"
    return "miss"


def long_appended_int(xs):
    for _ in range(600):
        xs.append(1)
    if xs[0] > 3:
        return "hit"
    return "miss"


def gains_later(xs, i, f):
    ys = xs[i:]
    ys.append(f)
    if ys[1] > 3.0:
        return "hit"
    return "miss"

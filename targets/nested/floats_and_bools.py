import math


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


def gains_later(xs, i, f):
    ys = xs[i:]
    ys.append(f)
    if ys[1] > 3.0:
        return "hit"
    return "miss"


def tracked_index_above(xs, i):
    if xs[i] > 3.0:
        return "hit"
    return "miss"


def truth_then_index(grid, i):
    if grid[i][0] and i == 0:
        return "hit"
    return "miss"


def float_of_item(xs, i):
    if float(xs[i]) > 3.0:
        return "hit"
    return "miss"


def key_to_another_kind(d, k):
    if d[k] > 3.0:
        return "hit"
    return "miss"


def two_keys(d, a, b):
    if d[a][b] == 7:
        return "seven"
    if d["x"]["p"] == 1:
        return "one"
    return "other"


def row_and_key(rows, i, k):
    if rows[i][k] == 7:
        return "seven"
    if rows[0]["a"] == 1:
        return "one"
    return "other"


def last_row_key(rows, k):
    row = rows[-1]
    if row["a"] == 1 and row[k] == 7:
        return "hit"
    return "miss"


def joined_int_row(ys, grid):
    row = (ys + grid)[1]
    if row[0] > 3:
        return "hit"
    return "miss"


def appended_then_read(xs, i, f):
    xs.append(f)
    if xs[i] > 3.0:
        return "hit"
    return "miss"


def flag_indexes(ys, flags):
    if ys[flags[0]] > 5:
        return "hit"
    return "miss"


def flag_pops(ys, flags):
    ys.pop(flags[0])
    if ys[0] > 5:
        return "hit"
    return "miss"


def flag_cuts_a_list(ys, flags):
    if ys[flags[0] :][0] > 5:
        return "hit"
    return "miss"


def flag_stores(ys, flags):
    ys[flags[0]] = 0
    if ys[1] > 5:
        return "hit"
    return "miss"


def flag_repeats_a_list(ys, flags):
    if (ys * flags[0])[0] > 5:
        return "hit"
    return "miss"


def flag_cuts_a_str(s, flags):
    if s[flags[0] :] == "bc":
        return "hit"
    return "miss"


def flag_repeats_a_str(s, flags):
    if s * flags[0] == "bc":
        return "hit"
    return "miss"


def flag_picks_a_char(s, flags):
    if s[flags[0]] == "z":
        return "hit"
    return "miss"


def float_as_int_pads(s, xs):
    if s.ljust(int(xs[0])) == "b  ":
        return "hit"
    return "miss"


def float_as_int_indexes(ys, xs):
    if ys[int(xs[0])] > 5:
        return "hit"
    return "miss"


def flag_value_indexes(ys, data):
    if ys[data["flag"]] > 5:
        return "hit"
    return "miss"


def flag_as_a_key(d: dict[int, int], flags):
    if d[flags[0]] > 5:
        return "hit"
    return "miss"


def flag_searches_keys(d: dict[int, int], flags):
    if flags[0] in d and d[0] > 5:
        return "hit"
    return "miss"


def rounds_in_a_walk(d, xs):
    for k in d:
        round(xs[0], 1)
        if k == "target":
            return "hit"
    return "miss"


def formats_in_a_walk(d, xs):
    for k in d:
        f"{xs[0]:.1f}"
        if k == "target":
            return "hit"
    return "miss"


def percent_in_a_walk(d, xs):
    for k in d:
        "%.1f" % xs[0]
        if k == "target":
            return "hit"
    return "miss"


def powers_in_a_walk(d, xs):
    for k in d:
        xs[0] ** 2
        if k == "target":
            return "hit"
    return "miss"


def cut_row_in_a_walk(d, g, i):
    for k in d:
        if g[i:][0][0] > 1.0:
            pass
        if k == "target":
            return "hit"
    return "miss"


def picked_dict_in_a_walk(d, rows, i):
    for k in d:
        if rows[i]["x"] > 1.0:
            pass
        if k == "target":
            return "hit"
    return "miss"


def flag_in_a_walk(d, ys, flags):
    for k in d:
        ys[flags[0]]
        if k == "target":
            return "hit"
    return "miss"


def flag_value_in_a_sum(ys, data):
    if ys[data["flag"] + 1] > 5:
        return "hit"
    return "miss"


def percent_beside_a_name(name, scores):
    if "%s=%.1f" % (name, scores[0]) == "bob=0.5":
        return "hit"
    return "miss"


def key_as_a_float_in_a_format(d: dict[int, int]):
    for k in d:
        t = "%.1f" % (k * 0.5)
        if t == "0.5" and k == 7:
            return "never"
        if k == 7:
            return "seven"
    return "none"


def key_as_a_tolerance(d: dict[int, int]):
    for k in d:
        close = math.isclose(1.0, 1.5, abs_tol=k * 0.5)
        if close and k == 7:
            return "never"
        if k == 7:
            return "seven"
    return "none"


def name_beside_a_float(s, xs):
    if "%s%s" % (s, xs[0]) == "zz0.5":
        return "hit"
    return "miss"

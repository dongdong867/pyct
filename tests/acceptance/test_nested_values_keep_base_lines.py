"""Every line base covers stays covered once a float or a bool inside an argument is tracked: under
tracked keys and joins, where such a number is a position or a key, and across a dict's walk."""

import pytest

from tests.acceptance.test_nested_floats_and_bools import (
    NESTED,
    QUICK,
    lines_of,
    missing_lines,
    return_line,
)


@pytest.mark.parametrize(
    ("function", "seed"),
    [
        ("two_keys", {"d": {"x": {"p": 1, "q": 5}}, "a": "x", "b": "p"}),
        ("row_and_key", {"rows": [{"a": 1, "b": 5}], "i": 0, "k": "a"}),
        ("last_row_key", {"rows": [{"a": 1, "b": 2}], "k": "a"}),
        ("joined_int_row", {"ys": [[1]], "grid": [[2], [0.5]]}),
        ("joined_int_row", {"ys": [[1]], "grid": [[2], 0.5]}),
        ("joined_int_row", {"ys": [[1]], "grid": [[2], True]}),
        ("joined_int_row", {"ys": [[1]], "grid": [[2], 0.5, 1]}),
        ("appended_then_read", {"xs": [1], "i": 1, "f": 0.5}),
        ("flag_indexes", {"ys": [0, 1], "flags": [False]}),
        ("flag_pops", {"ys": [0, 1], "flags": [False]}),
        ("flag_cuts_a_list", {"ys": [0, 1], "flags": [False]}),
        ("flag_stores", {"ys": [0, 1], "flags": [False]}),
        ("flag_repeats_a_list", {"ys": [0, 1], "flags": [True]}),
        ("flag_cuts_a_str", {"s": "abc", "flags": [True]}),
        ("flag_repeats_a_str", {"s": "ab", "flags": [True]}),
        ("flag_picks_a_char", {"s": "abc", "flags": [True]}),
        ("float_as_int_pads", {"s": "a", "xs": [3.5]}),
        ("float_as_int_indexes", {"ys": [0, 1, 2], "xs": [1.5]}),
        ("flag_value_indexes", {"ys": [0, 1], "data": {"flag": False}}),
        ("flag_as_a_key", {"d": {"0": 1}, "flags": [False]}),
        ("flag_searches_keys", {"d": {"0": 1}, "flags": [False]}),
        ("rounds_in_a_walk", {"d": {"a": 1}, "xs": [0.5]}),
        ("formats_in_a_walk", {"d": {"a": 1}, "xs": [0.5]}),
        ("percent_in_a_walk", {"d": {"a": 1}, "xs": [0.5]}),
        ("powers_in_a_walk", {"d": {"a": 1}, "xs": [0.5]}),
        ("flag_in_a_walk", {"d": {"a": 1}, "ys": [0, 1], "flags": [False]}),
    ],
)
def test_a_line_base_covers_stays_covered(function: str, seed: object) -> None:
    target = f"{NESTED}::{function}"
    lines = lines_of(target, seed, *QUICK)
    assert missing_lines(target, lines) == set()


@pytest.mark.parametrize(
    ("function", "seed"),
    [
        ("cut_row_in_a_walk", {"d": {"a": 1}, "g": [[0.5], [0.5]], "i": 1}),
        ("picked_dict_in_a_walk", {"d": {"a": 1}, "rows": [{"x": 0.5}, {"x": 0.5}], "i": 1}),
    ],
)
def test_a_float_left_plain_in_a_walk_lets_the_walk_choose_a_key(
    function: str, seed: object
) -> None:
    target = f"{NESTED}::{function}"
    lines = lines_of(target, seed, *QUICK)
    assert return_line(target, "hit") not in missing_lines(target, lines)

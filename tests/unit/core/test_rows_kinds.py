"""What a list of rows holds, which a read of a row an index picks says its kind by."""

from typing import Any

from pyct.binding.bind import bind


def head_of(item: Any) -> object:
    return item.expression[0]


def test_what_the_rows_hold_is_worked_out_once_until_a_list_changes() -> None:
    args: Any = bind({"g": [[1], [2]], "i": 0}, [])
    rows = args["g"]

    _ = rows[args["i"]], rows[-1]
    kept = rows.__dict__["rows_kinds"]
    _ = rows[-1]

    assert rows.__dict__["rows_kinds"] is kept


def test_a_row_picked_after_a_change_says_the_kind_the_change_added() -> None:
    args: Any = bind({"g": [[1], [2]], "i": 0, "f": 0.5}, [])
    rows = args["g"]
    _ = rows[args["i"]]
    rows[1].append(args["f"])

    item = rows[args["i"]][0]

    assert head_of(item) == "[int]"


def test_a_change_that_adds_no_kind_keeps_what_the_rows_hold() -> None:
    args: Any = bind({"g": [[1], [2]], "i": 0}, [])
    rows = args["g"]
    _ = rows[args["i"]]
    kept = rows.__dict__["rows_kinds"]

    rows[1].append(3)
    _ = rows[args["i"]]

    assert rows.__dict__["rows_kinds"] is kept


def test_a_read_says_the_same_kind_after_another_read_of_its_row() -> None:
    args: Any = bind({"g": [[[1], [1]], [[2], 0.5]], "i": 0, "j": 0}, [])
    g, i, j = args["g"], args["i"], args["j"]
    before = head_of(g[i][j][0])

    _ = g[0][j]

    assert head_of(g[i][j][0]) == before

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

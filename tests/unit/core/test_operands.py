"""A number read out of a container, as a position or a key: the number is plain, the receiver is
not."""

from typing import Any

import pytest

from pyct.binding.bind import bind
from pyct.core.branch import KEPT, Downgrade, Fact, SinkItem
from pyct.core.ints import ConcolicInt
from pyct.core.strs import ConcolicStr


def bound(args: dict[str, object]) -> tuple[Any, list[SinkItem]]:
    sink: list[SinkItem] = []
    return bind(args, sink), sink


def named(sink: list[SinkItem]) -> list[str]:
    return [item.name for item in sink if isinstance(item, Downgrade)]


def kept(sink: list[SinkItem]) -> list[object]:
    forms = [item.expression for item in sink if isinstance(item, Fact)]
    return [form[1] for form in forms if isinstance(form, list) and form[0] == KEPT]


def test_a_bool_item_indexes_a_list_that_stays_tracked() -> None:
    args, sink = bound({"ys": [3, 4], "flags": [True]})

    item = args["ys"][args["flags"][0]]

    assert type(item) is ConcolicInt and item == 4
    assert named(sink) == ["__getitem__"]
    assert kept(sink) == [["==", ["[bool]", "flags", 0], True]]


def test_a_bool_item_cuts_a_str_that_stays_tracked() -> None:
    args, sink = bound({"s": "abc", "flags": [True]})

    piece = args["s"][args["flags"][0] :]

    assert type(piece) is ConcolicStr and piece == "bc"
    assert named(sink) == ["__getitem__"]


def test_a_bool_value_of_a_dict_indexes_a_list_that_stays_tracked() -> None:
    args, sink = bound({"ys": [3, 4], "data": {"flag": False}})

    item = args["ys"][args["data"]["flag"]]

    assert type(item) is ConcolicInt and item == 3
    assert named(sink) == ["__getitem__"]


def test_a_bool_parameter_keeps_its_downgrade_of_the_list() -> None:
    args, _ = bound({"ys": [3, 4], "flag": True})

    assert type(args["ys"][args["flag"]]) is int


def test_an_int_item_stays_a_tracked_index() -> None:
    args, sink = bound({"ys": [3, 4], "ks": [1]})

    item = args["ys"][args["ks"][0]]

    assert type(item) is ConcolicInt
    assert named(sink) == []


@pytest.mark.parametrize("flag", [True, False])
def test_a_bool_item_used_as_a_key_reads_as_its_plain_value(flag: bool) -> None:
    args, sink = bound({"d": {"a": 1}, "flags": [flag]})

    assert (args["flags"][0] in args["d"]) is False
    assert named(sink) == ["__contains__"]


def test_a_float_item_raises_as_an_index_as_python_does() -> None:
    args, _ = bound({"ys": [3], "xs": [0.5]})

    with pytest.raises(TypeError):
        args["ys"][args["xs"][0]]

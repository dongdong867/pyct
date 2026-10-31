"""A tracked list's shape in the input, and a list answered back at its new length; a tracked
dict's made-up keys."""

import pytest

from pyct.binding.annotations import Items, OneOf
from pyct.binding.shapes import (
    ArrayValue,
    DictAnswer,
    DictShape,
    ListAnswer,
    ListShape,
    annotated,
    dict_shaped,
    empty,
    rekeyed,
    resized,
    shaped,
)


def test_a_shape_runs_the_input_in_stretches_of_one_kind() -> None:
    shape = shaped([1, 2, "a", None, None, 3], {}, None)

    assert shape.runs() == (
        ("int", 0, 2),
        ("str", 2, 3),
        ("none", 3, 5),
        ("int", 5, 6),
    )
    assert shape.fill == "none"


def test_an_added_item_takes_the_kind_the_items_share_or_the_annotations() -> None:
    assert shaped([1, 2], {}, str).fill == "int"
    assert shaped([], {}, str).fill == "str"
    assert shaped([1, "a"], {}, int).fill == "int"
    assert shaped([], {}, None).fill == "none"


def test_the_annotation_names_the_kind_of_an_added_item() -> None:
    assert annotated(int) == "int" and annotated(str) == "str"
    assert annotated(float) == "float" and annotated(bool) == "bool"
    assert annotated(None) == "none"
    assert annotated(OneOf((int, type(None)))) == "int"
    # the first kind the annotation names, so the item passes the seed check the seed passed
    assert annotated(OneOf((str, int))) == "str"
    assert annotated(OneOf((type(None), float))) == "float"
    assert annotated(Items(list, None)) == "list"
    assert annotated(Items(dict, None)) == "dict"


def test_a_list_added_inside_a_list_starts_empty_with_its_annotations_kind() -> None:
    # a list whose items are lists of strs: an added item is an empty list of strs
    rows = empty(Items(list, str))

    assert rows == ListShape((), fill="list", fill_row=ListShape((), fill="str"))
    assert rows.row_at(0) == ListShape((), fill="str")


def test_a_list_at_its_answered_length_keeps_what_no_fork_read() -> None:
    shape = ListShape(("int", "str"), fill="dict")
    answer = ListAnswer(length=4, arrays={"int": ArrayValue(7, {0: 9})}, read=frozenset({0, 1}))

    # a read str position keeps the input's: no str array came back; added dicts start empty
    assert resized([1, "a"], answer, shape) == [9, "a", {}, {}]


def test_an_added_float_or_bool_no_fork_read_holds_its_zero() -> None:
    answer = ListAnswer(length=2)

    # the seed check accepts the type's own zero, where null would be refused
    assert resized([], answer, ListShape((), fill="float")) == [0.0, 0.0]
    assert resized([], answer, ListShape((), fill="bool")) == [False, False]


def test_an_added_float_or_bool_no_fork_read_holds_its_zero_whatever_the_array_says() -> None:
    nan = float("nan")
    floats = ListAnswer(length=2, arrays={"float": ArrayValue(nan, {0: 2.5})}, read=frozenset({0}))
    bools = ListAnswer(length=2, arrays={"bool": ArrayValue(True)}, read=frozenset({1}))

    # an array's default is what cvc5 chose for a position no fork asks about
    assert resized([], floats, ListShape((), fill="float")) == [2.5, 0.0]
    assert resized([], bools, ListShape((), fill="bool")) == [False, True]


def test_an_added_int_or_str_takes_the_array_s_default_as_it_did() -> None:
    answer = ListAnswer(length=1, arrays={"int": ArrayValue(7)})

    assert resized([], answer, ListShape((), fill="int")) == [7]


@pytest.mark.parametrize(
    ("shape", "mixed"),
    [
        (ListShape(("int", "float")), True),
        (ListShape(("int", "none")), True),
        (ListShape(("float", "float")), False),
        (ListShape(()), False),
        (
            ListShape(("list", "list"), rows={0: ListShape(("int",)), 1: ListShape(("float",))}),
            True,
        ),
        (
            ListShape(("list", "list"), rows={0: ListShape(("int",)), 1: ListShape(("int",))}),
            False,
        ),
    ],
)
def test_a_list_is_mixed_when_its_items_or_its_rows_do_not_share_a_kind(
    shape: ListShape, mixed: bool
) -> None:
    assert shape.mixed is mixed


@pytest.mark.parametrize(
    ("shape", "floats"),
    [
        (ListShape(("float",)), True),
        (ListShape(()), False),
        (ListShape((), fill="float"), True),
        (ListShape(("list",), rows={0: ListShape(("float",))}), True),
        (ListShape(("list",), rows={0: ListShape(("int",))}, fill="list"), False),
        (ListShape((), fill="list", fill_row=ListShape((), fill="float")), True),
    ],
)
def test_a_list_holds_floats_at_any_depth(shape: ListShape, floats: bool) -> None:
    assert shape.holds_floats is floats


def test_a_dict_holds_floats_by_its_values_or_what_the_solver_adds() -> None:
    assert DictShape(keys=("a",), kinds=("float",)).holds_floats
    assert DictShape(keys=(), kinds=(), fill="float").holds_floats
    assert not DictShape(keys=("a",), kinds=("int",), fill="int").holds_floats


def test_an_int_keyed_dict_makes_up_the_smallest_non_negative_ints_not_taken() -> None:
    shape = dict_shaped({0: 5}, Items(dict, int, int))

    assert shape.makes_up and shape.made_type is int
    # a str key and a negative int take no made-up int's place
    assert shape.made_up_keys({0, 1, "2", -1, 4}, 4) == [2, 3, 5, 6]
    assert rekeyed({0: 5}, DictAnswer({1: False}, kept=1, made=1), shape) == {0: 5, 2: 0}


def test_a_dict_makes_up_keys_only_when_its_keys_are_all_of_the_made_up_type() -> None:
    int_keys = Items(dict, int, int)

    assert dict_shaped({}, int_keys).makes_up and dict_shaped({1: 0}, int_keys).makes_up
    assert not dict_shaped({1: 0, "a": 0}, int_keys).makes_up
    assert not dict_shaped({"a": 0}, int_keys).makes_up
    str_keys = DictShape(keys=("a",), kinds=("int",))
    assert str_keys.makes_up and str_keys.made_up_keys({"pyct1"}, 2) == ["pyct2", "pyct3"]

"""A tracked list's shape in the input, and a list answered back at its new length; a tracked
dict's made-up keys."""

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


def test_an_added_item_the_annotation_types_as_a_float_or_a_bool_holds_its_plain_default() -> None:
    answer = ListAnswer(length=2)

    # nothing solves a float or a bool yet: the added item holds the type's own zero, which the
    # seed check accepts, where null would be refused
    assert resized([], answer, ListShape((), fill="float")) == [0.0, 0.0]
    assert resized([], answer, ListShape((), fill="bool")) == [False, False]


def test_an_int_keyed_dict_makes_up_the_smallest_non_negative_ints_not_taken() -> None:
    shape = dict_shaped({0: 5}, Items(dict, int, int))

    assert shape.makes_up and shape.made_type is int
    # a str key and a negative int take no made-up int's place
    assert shape.made_up({0, 1, "2", -1, 4}, 4) == [2, 3, 5, 6]
    assert rekeyed({0: 5}, DictAnswer({1: False}, kept=1, made=1), shape) == {0: 5, 2: 0}


def test_a_dict_makes_up_keys_only_when_its_keys_are_all_of_the_made_up_type() -> None:
    int_keys = Items(dict, int, int)

    assert dict_shaped({}, int_keys).makes_up and dict_shaped({1: 0}, int_keys).makes_up
    assert not dict_shaped({1: 0, "a": 0}, int_keys).makes_up
    assert not dict_shaped({"a": 0}, int_keys).makes_up
    str_keys = DictShape(keys=("a",), kinds=("int",))
    assert str_keys.makes_up and str_keys.made_up({"pyct1"}, 2) == ["pyct2", "pyct3"]

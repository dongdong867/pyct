"""A tracked list's shape in the input, and a list answered back at its new length."""

from pyct.binding.annotations import Items, OneOf
from pyct.binding.shapes import ArrayValue, ListAnswer, ListShape, annotated, empty, resized, shaped


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
    assert annotated(float) == "none" and annotated(None) == "none"
    assert annotated(OneOf((int, type(None)))) == "int"
    assert annotated(OneOf((int, str))) == "none"
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

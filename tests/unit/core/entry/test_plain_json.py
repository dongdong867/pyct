"""A value as plain JSON data, read through its base types."""

import json

import pytest

from pyct.core.entry.plain_json import plain_json
from pyct.core.foundation.branch import SinkItem
from pyct.core.lists.lists import ConcolicList
from pyct.core.numbers.ints import ConcolicInt
from pyct.core.strs.strs import ConcolicStr


def test_tracked_values_and_those_inside_a_list_or_dict_are_their_plain_values() -> None:
    sink: list[SinkItem] = []
    n = ConcolicInt.made(5, expression="n", sink=sink)
    key = ConcolicStr.made("k", expression="k", sink=sink)
    items = ConcolicList.made([n, 2], expression="xs", sink=sink)

    data = plain_json({key: items, "t": (True, None, 1.5)})

    assert json.dumps(data) == '{"k": [5, 2], "t": [true, null, 1.5]}'
    assert type(data["k"][0]) is int  # pyrefly: ignore[bad-index]
    assert sink == []


def test_a_tuple_is_a_list_unless_it_is_asked_not_to_be() -> None:
    assert plain_json([(1, 2)]) == [[1, 2]]
    with pytest.raises(TypeError, match="tuple is not a JSON value"):
        plain_json([(1, 2)], tuples=False)


@pytest.mark.parametrize(
    ("value", "words"),
    [
        ({1, 2}, "set is not a JSON value"),
        (b"ab", "bytes is not a JSON value"),
        ({1: 2}, "a key of type int is not one a JSON object holds"),
    ],
)
def test_a_part_json_holds_no_form_of_is_refused(value: object, words: str) -> None:
    with pytest.raises(TypeError, match=words):
        plain_json(value)


def test_a_value_past_the_count_asked_for_is_refused_before_it_is_read_whole() -> None:
    fits = ["ab"] * 3

    assert plain_json(fits, most=len(json.dumps(fits))) == fits
    with pytest.raises(ValueError, match="more than"):
        plain_json(["a" * 10], most=10)
    with pytest.raises(ValueError, match="more than"):
        plain_json(list(range(10**6)), most=2048)


def test_a_value_that_lies_about_its_class_is_read_by_its_own_type() -> None:
    class Lying:
        @property
        def __class__(self) -> type:  # pyrefly: ignore[bad-override]
            raise AssertionError("read")

    with pytest.raises(TypeError, match="Lying is not a JSON value"):
        plain_json([Lying()])

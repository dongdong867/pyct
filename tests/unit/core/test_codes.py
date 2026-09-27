"""A tracked string's length and code, and the character of a tracked code: `len`, `ord`, `chr`."""

import pytest

from pyct.core import codes, strs
from pyct.core.branch import Branch, SinkItem
from pyct.core.ints import ConcolicInt
from pyct.core.strs import ConcolicStr
from pyct.core.values import raised_by_target


def sides(sink: list[SinkItem]) -> list[tuple[object, bool]]:
    """Each fork in the sink as its expression and the side it took."""
    assert all(isinstance(item, Branch) for item in sink), sink
    return [(item.expression, item.taken) for item in sink if isinstance(item, Branch)]


def python_raise(operation: object, *args: object) -> tuple[type, str]:
    """The exception type and message plain Python gives for this call, in this run."""
    with pytest.raises(Exception) as caught:
        operation(*args)  # pyrefly: ignore[not-callable]
    return type(caught.value), str(caught.value)


def test_the_length_of_a_tracked_string_is_a_tracked_int_and_records_nothing() -> None:
    sink: list[SinkItem] = []

    size = strs.length(ConcolicStr("abc", expression="s", sink=sink))

    assert type(size) is ConcolicInt
    assert int.__int__(size) == 3
    assert size.expression == ["len", "s"]
    assert size.sink is sink
    assert sink == []


def test_the_code_of_one_character_is_a_tracked_int_past_its_one_character_fork() -> None:
    sink: list[SinkItem] = []

    code = codes.code(ConcolicStr("A", expression="c", sink=sink))

    assert type(code) is ConcolicInt
    assert int.__int__(code) == 65
    assert code.expression == ["ord", "c"]
    assert sides(sink) == [(["==", ["len", "c"], 1], True)]


@pytest.mark.parametrize("value", ["", "ab"])
def test_the_code_of_anything_but_one_character_records_its_fork_and_raises_as_python_does(
    value: str,
) -> None:
    sink: list[SinkItem] = []

    with pytest.raises(TypeError) as caught:
        codes.code(ConcolicStr(value, expression="c", sink=sink))

    assert (TypeError, str(caught.value)) == python_raise(ord, value)
    assert raised_by_target(caught.value)
    assert sides(sink) == [(["==", ["len", "c"], 1], False)]


def test_the_character_of_a_code_is_a_tracked_string_past_its_two_range_forks() -> None:
    sink: list[SinkItem] = []

    character = codes.character(ConcolicInt(122, expression="n", sink=sink))

    assert type(character) is ConcolicStr
    assert str.__str__(character) == "z"
    assert character.expression == ["chr", "n"]
    assert sides(sink) == [([">=", "n", 0], True), (["<=", "n", 1114111], True)]


@pytest.mark.parametrize("value", [0, 1114111])
def test_the_character_of_each_end_of_the_range_is_python_s(value: int) -> None:
    sink: list[SinkItem] = []

    character = codes.character(ConcolicInt(value, expression="n", sink=sink))

    assert str.__str__(character) == chr(value)
    assert [taken for _, taken in sides(sink)] == [True, True]


@pytest.mark.parametrize(
    ("value", "taken"),
    [(-1, [False]), (1114112, [True, False])],
)
def test_a_code_out_of_range_records_the_fork_it_fails_and_raises_as_python_does(
    value: int, taken: list[bool]
) -> None:
    sink: list[SinkItem] = []

    with pytest.raises(ValueError) as caught:
        codes.character(ConcolicInt(value, expression="n", sink=sink))

    assert (ValueError, str(caught.value)) == python_raise(chr, value)
    assert raised_by_target(caught.value)
    assert [side for _, side in sides(sink)] == taken


def test_the_code_of_a_character_read_at_a_position_records_no_length_fork() -> None:
    sink: list[SinkItem] = []

    code = codes.code(ConcolicStr("e", expression=["[]", "s", 0], sink=sink))

    assert (int.__int__(code), code.expression) == (101, ["ord", ["[]", "s", 0]])
    assert sink == []

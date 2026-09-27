"""A join of tracked strings: the tracked str it hands back, the walk it makes of a tracked list
first, and the raises and downgrades Python's own join would give."""

import heapq
from collections.abc import Callable, Iterator

import pytest

from pyct.core import substitutes
from pyct.core.branch import SinkItem
from pyct.core.ints import ConcolicInt
from pyct.core.strs import ConcolicStr
from pyct.core.values import raised_by_target
from tests.unit.core.test_list_reads import downgrades, forks, tracked

# a character past the last one cvc5 holds
PAST_CVC5 = "\U00030000"


def _separator(value: str = "-", sink: list[SinkItem] | None = None) -> ConcolicStr:
    return ConcolicStr.made(value, expression="sep", sink=[] if sink is None else sink)


def _python_raises(call: Callable[..., object], *args: object, **kwargs: object) -> str:
    """What plain Python's own call raises, in its words."""
    with pytest.raises(TypeError) as raised:
        call(*args, **kwargs)
    return str(raised.value)


def test_a_tracked_separator_joins_a_plain_list_as_a_display_of_its_items() -> None:
    sep = _separator()

    joined = sep.join(["a", "b"])

    assert type(joined) is ConcolicStr and str.__str__(joined) == "a-b"
    assert joined.expression == ["join", "sep", ["[,]", "'a'", "'b'"]]
    assert joined.sink is sep.sink and sep.sink == []


def test_a_literal_s_join_walks_a_tracked_list_first_and_writes_its_form() -> None:
    parts, sink = tracked(["x", "y"], name="parts")

    joined = substitutes.join("-".join, parts)

    assert str.__str__(joined) == "x-y"
    assert joined.expression == ["join", "'-'", "parts"]
    assert forks(sink) == [
        ([">", ["len", "parts"], 0], True),
        ([">", ["len", "parts"], 1], True),
        ([">", ["len", "parts"], 2], False),
    ]
    assert downgrades(sink) == []


def test_a_join_of_an_empty_tracked_list_is_the_empty_string_after_its_walk() -> None:
    parts, sink = tracked([], name="parts")

    joined = substitutes.join("-".join, parts)

    assert type(joined) is ConcolicStr and str.__str__(joined) == ""
    assert joined.expression == ["join", "'-'", "parts"]
    assert forks(sink) == [([">", ["len", "parts"], 0], False)]


def test_a_literal_s_join_of_a_built_list_writes_each_item_it_read() -> None:
    a = ConcolicStr.made("p", expression="a", sink=[])

    joined = substitutes.join("-".join, [a, "q"])

    assert str.__str__(joined) == "p-q"
    assert joined.expression == ["join", "'-'", ["[,]", "a", "'q'"]]
    assert joined.sink is a.sink


def test_a_generator_is_written_as_a_display_of_what_it_handed_out() -> None:
    parts, _ = tracked(["x"], name="parts")

    joined = substitutes.join("".join, (part.upper() for part in parts))

    assert str.__str__(joined) == "X"
    assert joined.expression == ["join", "''", ["[,]", ["upper", ["[]", "parts", 0]]]]


def test_a_tracked_str_is_joined_as_the_characters_its_walk_hands_out() -> None:
    s = ConcolicStr.made("ab", expression="s", sink=[])

    joined = substitutes.join(",".join, s)

    assert str.__str__(joined) == "a,b"
    assert joined.expression == ["join", "','", ["[,]", ["[]", "s", 0], ["[]", "s", 1]]]


def test_a_join_of_nothing_tracked_is_str_s_own_plain_answer() -> None:
    joined = substitutes.join("-".join, iter(["a", "b"]))

    assert type(joined) is str and joined == "a-b"


def test_a_list_turned_plain_by_its_walk_is_joined_as_python_joins_it() -> None:
    parts, sink = tracked(["b", "a"], name="parts")
    heapq.heappush(parts, "c")

    joined = substitutes.join("-".join, parts)

    assert type(joined) is str and joined == "b-a-c"
    assert downgrades(sink) == ["__iter__"]


def test_a_separator_given_no_iterable_raises_python_s_own_refusal() -> None:
    sep = _separator()

    with pytest.raises(TypeError) as raised:
        sep.join(ConcolicInt.made(5, expression="n", sink=sep.sink))

    assert str(raised.value) == _python_raises("-".join, 5)
    assert raised_by_target(raised.value)
    assert sep.sink == []


def test_an_item_that_is_not_a_str_raises_naming_the_type_it_reports() -> None:
    parts, sink = tracked(["a", 1], name="parts")

    with pytest.raises(TypeError) as raised:
        substitutes.join("-".join, parts)

    assert str(raised.value) == _python_raises("-".join, ["a", 1])
    assert raised_by_target(raised.value)
    assert downgrades(sink) == []


def test_a_raise_in_a_generator_is_the_target_s() -> None:
    def broken() -> Iterator[str]:
        yield "a"
        raise ValueError("broken")

    with pytest.raises(ValueError, match="broken") as raised:
        _separator().join(broken())

    assert raised_by_target(raised.value)


@pytest.mark.parametrize(
    ("separator", "item"), [(PAST_CVC5, "x"), ("-", PAST_CVC5)], ids=["separator", "item"]
)
def test_a_character_past_cvc5_is_python_s_answer_and_a_join_downgrade(
    separator: str, item: str
) -> None:
    parts, sink = tracked(["x", item], name="parts")

    joined = substitutes.join(separator.join, parts)

    assert type(joined) is str and joined == separator.join(["x", item])
    assert downgrades(sink) == ["join"]


def test_a_tracked_separator_called_in_another_form_is_str_s_own() -> None:
    sep = _separator()

    with pytest.raises(TypeError) as raised:
        sep.join()  # pyrefly: ignore[missing-argument]

    assert str(raised.value) == _python_raises(str.join, "-")
    assert sep.sink == []


def test_any_other_literal_join_call_is_the_method_s_own() -> None:
    with pytest.raises(TypeError) as raised:
        substitutes.join("-".join, iterable=["a"])

    assert str(raised.value) == _python_raises("-".join, iterable=["a"])


def test_a_tracked_int_in_a_plain_list_raises_naming_the_type_it_reports() -> None:
    items = ["a", ConcolicInt.made(1, expression="n", sink=[])]

    with pytest.raises(TypeError) as raised:
        substitutes.join("-".join, items)

    assert str(raised.value) == _python_raises("-".join, ["a", 1])


@pytest.mark.parametrize("items", [["a", "b"], ("a", "b")], ids=["list", "tuple"])
def test_a_plain_list_or_tuple_of_plain_values_is_the_method_s_own(items: object) -> None:
    joined = substitutes.join("-".join, items)

    assert type(joined) is str and joined == "a-b"


def test_a_plain_item_that_is_not_a_str_beside_a_tracked_one_raises_python_s_words() -> None:
    items = [ConcolicStr.made("a", expression="a", sink=[]), None]

    with pytest.raises(TypeError) as raised:
        substitutes.join("-".join, items)

    assert str(raised.value) == _python_raises("-".join, ["a", None])


class Refusing:
    """An object of the target's whose `__iter__` refuses, counting each time it is asked."""

    def __init__(self) -> None:
        self.asked = 0

    def __iter__(self) -> Iterator[str]:
        self.asked += 1
        raise TypeError("not iterable today")


@pytest.mark.parametrize(
    "join",
    [lambda value: substitutes.join("-".join, value), lambda value: _separator().join(value)],
    ids=["literal", "tracked"],
)
def test_an_iter_that_refuses_is_asked_once_as_python_asks_it(
    join: Callable[[object], object],
) -> None:
    python, pyct = Refusing(), Refusing()
    message = _python_raises("-".join, python)

    with pytest.raises(TypeError) as raised:
        join(pyct)

    assert str(raised.value) == message
    assert pyct.asked == python.asked == 1


def test_a_type_error_inside_a_generator_is_the_generator_s_own() -> None:
    def broken() -> Iterator[str]:
        yield "a"
        raise TypeError("broken")

    with pytest.raises(TypeError, match="broken"):
        substitutes.join("-".join, broken())

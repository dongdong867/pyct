"""A tracked list searched and compared, item by item as Python does it."""

import heapq

import pytest

from pyct.core.bools import ConcolicBool
from pyct.core.branch import Downgrade, SinkItem
from pyct.core.ints import ConcolicInt
from pyct.core.list_forms import UNWRITTEN, displayed, written
from pyct.core.list_state import is_static, kind_of
from pyct.core.lists import ConcolicList
from pyct.core.strs import ConcolicStr
from tests.unit.core.test_list_reads import downgrades, forks, tracked


def test_in_compares_each_item_until_one_matches() -> None:
    items, sink = tracked([1, 7, 9])

    assert 7 in items

    assert forks(sink) == [
        ([">", ["len", "items"], 0], True),
        (["==", ["[]", "items", 0], 7], False),
        ([">", ["len", "items"], 1], True),
        (["==", ["[]", "items", 1], 7], True),
    ]


def test_in_that_finds_nothing_ends_with_the_walk() -> None:
    items, sink = tracked([1])

    assert 7 not in items

    assert forks(sink)[-1] == ([">", ["len", "items"], 1], False)


def test_index_count_and_remove_search_as_pythons_do() -> None:
    items, sink = tracked([4, 5, 4])

    assert items.index(4) == 0
    assert items.count(4) == 2
    items.remove(5)

    assert items.expression == ["+", ["[:]", "items", None, 1], ["[:]", "items", 2, None]]
    with pytest.raises(ValueError, match="is not in list"):
        items.index(9)
    assert downgrades(sink) == []


def test_an_item_that_is_the_value_itself_matches_without_a_compare() -> None:
    sink: list[object] = []
    row = ConcolicList.made([], ["[]", "grid", 0], sink)  # pyrefly: ignore[bad-argument-type]
    grid = ConcolicList.made([row], "grid", sink)  # pyrefly: ignore[bad-argument-type]

    assert row in grid
    assert grid.index(row) == 0


def test_equal_lists_compare_their_lengths_first_then_each_pair() -> None:
    items, sink = tracked([1, 2])

    equal, unequal, shorter = items == [1, 2], items != [1, 2], items == [1]

    assert equal and not unequal and not shorter

    assert forks(sink)[:3] == [
        (["==", ["len", "items"], 2], True),
        (["==", ["[]", "items", 0], 1], True),
        (["==", ["[]", "items", 1], 2], True),
    ]
    assert forks(sink)[-1] == (["==", ["len", "items"], 1], False)


def test_two_tracked_lists_compare_both_lengths() -> None:
    items, sink = tracked([1])
    other, _ = tracked([1], name="other")

    assert items == other

    assert forks(sink)[0] == (["==", ["len", "items"], ["len", "other"]], True)


def test_an_order_answers_with_the_first_pair_that_differs() -> None:
    items, sink = tracked([0])

    below = items < [5]

    assert isinstance(below, ConcolicBool) and bool(below)
    assert forks(sink) == [
        ([">", ["len", "items"], 0], True),
        (["==", ["[]", "items", 0], 5], False),
        (["<", ["[]", "items", 0], 5], True),
    ]


def test_an_order_between_lists_equal_as_far_as_both_go_answers_by_length() -> None:
    items, sink = tracked([5])

    answers = [items < [5, 1], items <= [5], items > [], items >= [5, 0]]

    assert all(isinstance(answer, ConcolicBool) for answer in answers)
    assert [answer.expression for answer in answers] == [  # pyrefly: ignore[missing-attribute]
        ["<", ["len", "items"], 2],
        ["<=", ["len", "items"], 1],
        [">", ["len", "items"], 0],
        [">=", ["len", "items"], 2],
    ]
    assert [int.__bool__(answer) for answer in answers] == [True, True, True, False]  # pyrefly: ignore[bad-argument-type]


def test_a_compare_with_a_value_that_is_not_a_list_is_pythons_own() -> None:
    items, sink = tracked([1])

    unequal, equal = items != 1, items == (1,)

    assert unequal and not equal
    with pytest.raises(TypeError):
        items < (1,)  # noqa: B015

    assert forks(sink) == [] and downgrades(sink) == []


def test_a_compare_goes_plain_where_a_change_outside_the_methods_shows() -> None:
    items, sink = tracked([3, 9])
    other, _ = tracked([3, 9], name="other")

    heapq.heappush(other, 1)
    equal = items == other

    # the other list holds three items where its form says two: it is plain before any fork
    # reads its length, so the lengths compare as one tracked length and a number
    assert not equal and other.expression is None
    assert forks(sink)[-1] == (["==", ["len", "items"], 3], False)
    assert downgrades(sink) == []


def test_a_search_goes_plain_where_a_change_outside_the_methods_shows() -> None:
    items, sink = tracked([3, 9])

    list.append(items, 7)
    found = 7 in items

    assert found and downgrades(sink) == ["__contains__"]
    assert items.expression is None


def test_a_count_on_a_plain_list_is_pythons_own() -> None:
    items, sink = tracked([3, 3])

    items.lose("sort")

    assert items.count(3) == 2 and items.index(3) == 0
    assert downgrades(sink) == ["sort"] and forks(sink) == []


def test_each_kind_of_item_is_its_own() -> None:
    sink: list[object] = []
    row = ConcolicList.made([], "grid", sink)  # pyrefly: ignore[bad-argument-type]

    assert [kind_of(item) for item in (1, "a", True, 1.5, None, [], {}, row, object())] == [
        "int",
        "str",
        "bool",
        "float",
        "none",
        "list",
        "dict",
        "list",
        "other",
    ]
    assert kind_of(ConcolicStr("a", expression="s", sink=[])) == "str"


def test_a_form_is_static_when_it_names_an_argument_as_it_came() -> None:
    assert is_static("items")
    assert is_static(["[]", ["[]", "config", "'rows'"], 0])
    assert not is_static(["+", "items", ["[,]", 1]])
    assert not is_static(["[]", "items", ["+", "i", 1]])
    assert not is_static("'items'")


def test_a_display_writes_what_an_expression_holds_and_nothing_else() -> None:
    sink: list[object] = []
    x = ConcolicInt(1, expression="x", sink=sink)  # pyrefly: ignore[bad-argument-type]
    row = ConcolicList.made([], "row", sink)  # pyrefly: ignore[bad-argument-type]

    assert displayed([x, 2, "a", None, 1.5, True, [3], row], "append") == [
        "[,]",
        "x",
        2,
        "'a'",
        None,
        1.5,
        True,
        ["[,]", 3],
        "row",
    ]
    assert written({"k": 1}, "append") is UNWRITTEN
    assert written(object(), "append") is UNWRITTEN
    assert displayed([[object()]], "append") is UNWRITTEN


def test_a_list_changed_outside_its_methods_goes_into_a_display_as_the_values_it_holds() -> None:
    sink: list[SinkItem] = []
    row = ConcolicList.made([1], "row", sink)

    list.append(row, 2)

    assert written(row, "append") == ["[,]", 1, 2]
    assert row.expression is None
    assert [item.name for item in sink if isinstance(item, Downgrade)] == ["append"]


class _Appends:
    """A value whose first compare appends to a list without its methods, as target code may."""

    def __init__(self, items: list[object]) -> None:
        self.items = items
        self.appended = False

    def __eq__(self, other: object) -> bool:
        if not self.appended:
            self.appended = True
            list.append(self.items, 0)
        return False

    __hash__ = None  # type: ignore[assignment]


def test_a_search_that_changes_the_list_goes_on_as_pythons_own() -> None:
    items, sink = tracked([3, 9])

    found = items.count(_Appends(items))

    # the first compare appends: from the next step the list is plain, and Python's own search
    # compares the rest, the appended item among them
    assert found == 0 and items.expression is None
    assert downgrades(sink) == ["count"]

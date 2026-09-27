"""A tracked list read: its truth test, an index, a slice, and the walks from either end."""

import heapq
import pickle
from typing import Any

import pytest

from pyct.core.branch import Branch, Downgrade, Expression, SinkItem
from pyct.core.ints import ConcolicInt
from pyct.core.list_reads import handed
from pyct.core.list_state import plain
from pyct.core.lists import ConcolicList
from pyct.core.strs import ConcolicStr


def tracked(values: list[Any], name: str = "items") -> tuple[Any, list[SinkItem]]:
    """A tracked list of the values, each int and str tracked at its place, and its sink."""
    sink: list[SinkItem] = []
    items: list[object] = []
    for at, value in enumerate(values):
        access: Expression = ["[]", name, at]
        if isinstance(value, str):
            items.append(ConcolicStr(value, expression=access, sink=sink))
        elif isinstance(value, int) and not isinstance(value, bool):
            items.append(ConcolicInt(value, expression=access, sink=sink))
        else:
            items.append(value)
    return ConcolicList.made(items, name, sink), sink


def values(items: object) -> list[object]:
    """What a list holds, each item plain, read without recording anything."""
    assert isinstance(items, list)
    return [plain(item) for item in list.copy(items)]


def forks(sink: list[SinkItem]) -> list[tuple[Expression, bool]]:
    return [(item.expression, item.taken) for item in sink if isinstance(item, Branch)]


def downgrades(sink: list[SinkItem]) -> list[str]:
    return [item.name for item in sink if isinstance(item, Downgrade)]


def test_the_truth_test_is_the_length_against_zero() -> None:
    items, sink = tracked([1])
    empty, empty_sink = tracked([])

    assert bool(items) is True
    assert bool(empty) is False
    assert forks(sink) == [(["!=", ["len", "items"], 0], True)]
    assert forks(empty_sink) == [(["!=", ["len", "items"], 0], False)]


def test_an_index_records_the_long_enough_fork_and_hands_out_the_item_as_indexed() -> None:
    items, sink = tracked([1, 2, 3])

    first, last = items[0], items[-1]

    assert values([first, last]) == [1, 3]
    assert isinstance(last, ConcolicInt) and last.expression == ["[]", "items", -1]
    assert forks(sink) == [
        ([">", ["len", "items"], 0], True),
        ([">=", ["len", "items"], 1], True),
    ]


def test_an_index_past_the_end_raises_after_its_fork() -> None:
    items, sink = tracked([1, 2])

    with pytest.raises(IndexError):
        items[3]
    with pytest.raises(IndexError):
        items[-3]

    assert forks(sink) == [
        ([">", ["len", "items"], 3], False),
        ([">=", ["len", "items"], 3], False),
    ]


def test_a_tracked_index_records_both_ends_as_a_tracked_index_into_a_string_does() -> None:
    items, sink = tracked([1, 7])
    i = ConcolicInt(-1, expression="i", sink=sink)

    item = items[i]

    assert isinstance(item, ConcolicInt) and plain(item) == 7
    assert item.expression == ["[]", "items", "i"]
    assert forks(sink) == [
        ([">", ["len", "items"], "i"], True),
        ([">=", ["len", "items"], ["-", "i"]], True),
    ]


def test_a_tracked_index_past_either_end_stops_at_the_fork_it_fails() -> None:
    items, sink = tracked([1, 7])

    with pytest.raises(IndexError):
        items[ConcolicInt(2, expression="i", sink=sink)]
    with pytest.raises(IndexError):
        items[ConcolicInt(-3, expression="j", sink=sink)]

    assert forks(sink) == [
        ([">", ["len", "items"], "i"], False),
        ([">", ["len", "items"], "j"], True),
        ([">=", ["len", "items"], ["-", "j"]], False),
    ]


def test_a_tracked_index_into_items_of_two_kinds_is_a_downgrade() -> None:
    items, sink = tracked([1, "a"])

    item = items[ConcolicInt(1, expression="i", sink=sink)]

    assert type(item) is str and item == "a"
    assert downgrades(sink) == ["__getitem__"] and forks(sink) == []


def test_a_position_from_the_start_of_a_mixed_argument_is_read_by_its_position() -> None:
    items, sink = tracked([1, "a", None])

    one, text, nothing = items[0], items[1], items[2]

    assert isinstance(one, ConcolicInt) and isinstance(text, ConcolicStr)
    assert nothing is None
    assert downgrades(sink) == []


def test_a_position_from_the_end_of_a_mixed_list_hands_out_the_item_as_indexed() -> None:
    items, sink = tracked([1, "a"])

    last = items[-1]

    # the solver reads it by what the path does with it: the kinds leave it to the path
    assert isinstance(last, ConcolicStr) and last.expression == ["[]", "items", -1]
    assert downgrades(sink) == []


def test_a_list_inside_is_named_as_the_target_indexed_it_until_it_changes() -> None:
    sink: list[SinkItem] = []
    rows: list[Any] = [ConcolicList.made([], ["[]", "grid", at], sink) for at in range(2)]
    grid: Any = ConcolicList.made(rows, "grid", sink)
    i = ConcolicInt(0, expression="i", sink=sink)

    last = grid[-1]
    assert last.expression == ["[]", "grid", -1]
    first = grid[i]
    assert first.expression == ["[]", "grid", "i"]
    first.append(1)
    changed = first.expression
    assert grid[0] is first and first.expression is changed


def test_an_index_of_a_kind_pyct_does_not_follow_is_lists_own_answer() -> None:
    items, sink = tracked([1, 2])

    with pytest.raises(TypeError):
        items["a"]
    compared = items[ConcolicInt(1, expression="x", sink=sink) > 0]

    # a compare's answer is a position pyct does not follow: list's own read, named, and plain
    assert type(compared) is int and compared == 2
    assert downgrades(sink) == ["__getitem__"]


def test_a_slice_is_a_tracked_list_that_records_no_fork() -> None:
    items, sink = tracked([1, 2, 3, 4])
    n = ConcolicInt(1, expression="n", sink=sink)

    pieces = [items[1:3], items[n:], items[::-1], items[3:0:-1], items[:], items[::1]]

    assert [values(piece) for piece in pieces] == [
        [2, 3],
        [2, 3, 4],
        [4, 3, 2, 1],
        [4, 3, 2],
        [1, 2, 3, 4],
        [1, 2, 3, 4],
    ]
    assert [piece.expression for piece in pieces] == [
        ["[:]", "items", 1, 3],
        ["[:]", "items", "n", None],
        ["[:]", "items", None, None, -1],
        ["[:]", "items", 3, 0, -1],
        "items",
        "items",
    ]
    assert forks(sink) == []


def test_a_slice_pyct_does_not_follow_is_a_downgrade() -> None:
    items, sink = tracked([1, 2, 3])

    stepped = items[::2]
    tracked_step = items[:: ConcolicInt(2, expression="k", sink=sink)]

    # Python's own slice, its items plain
    assert type(stepped) is list and stepped == [1, 3]
    assert all(type(item) is int for item in [*stepped, *tracked_step])
    assert downgrades(sink) == ["__getitem__", "__getitem__"]


def test_a_walk_records_a_fork_for_each_item_and_one_where_it_ends() -> None:
    items, sink = tracked([5, 6])

    walked = list(iter(items))

    assert values(walked) == [5, 6]
    assert [item.expression for item in walked] == [["[]", "items", 0], ["[]", "items", 1]]
    assert forks(sink) == [
        ([">", ["len", "items"], 0], True),
        ([">", ["len", "items"], 1], True),
        ([">", ["len", "items"], 2], False),
    ]


def test_a_walk_reads_the_form_afresh_at_each_step() -> None:
    items, sink = tracked([5])

    for item in items:
        if len(items.storage()) < 2:
            items.append(item)

    grown = ["+", "items", ["[,]", ["[]", "items", 0]]]
    assert forks(sink)[-1] == ([">", ["len", grown], 2], False)


def test_a_walk_goes_plain_where_a_change_outside_the_methods_shows() -> None:
    items, sink = tracked([3, 9])
    walk = iter(items)

    first = next(walk)
    heapq.heappush(items, 0)
    rest = list(walk)

    assert isinstance(first, ConcolicInt)
    # the walk goes on as Python's own, and the list holds plain values from then on
    assert rest == [9, 3] and all(type(item) is int for item in rest)
    assert downgrades(sink) == ["__iter__"]
    # heapq's own compare of a tracked item is a fork Python took; after it, nothing more
    assert forks(sink)[1] == ([">", ["[]", "items", 0], 0], True)
    assert type(items[0]) is int and 3 in items and items == [0, 9, 3]
    assert downgrades(sink) == ["__iter__"] and len(forks(sink)) == 2


def test_reversed_walks_from_the_end_each_item_counted_back() -> None:
    items, sink = tracked([5, 6])

    walked = list(reversed(items))

    assert values(walked) == [6, 5]
    assert [item.expression for item in walked] == [["[]", "items", -1], ["[]", "items", -2]]
    assert forks(sink)[-1] == ([">", ["len", "items"], 2], False)


def test_reversed_goes_plain_when_the_length_changes_while_it_walks() -> None:
    items, sink = tracked([5, 6, 7])
    walk = reversed(items)

    first = next(walk)
    items.pop()
    rest = list(walk)

    assert plain(first) == 7 and values(rest) == [6, 5]
    assert downgrades(sink) == ["__reversed__"]


def test_len_is_a_downgrade_but_for_the_size_a_walk_just_started_asks_for() -> None:
    items, sink = tracked([1, 2])

    size = len(items)
    copied = list(items)

    assert size == 2 and values(copied) == [1, 2]
    assert downgrades(sink) == ["__len__"]


def test_an_item_that_is_a_list_is_handed_out_as_it_is_stored() -> None:
    sink: list[SinkItem] = []
    row = ConcolicList.made([], ["[]", "grid", 0], sink)
    grid = ConcolicList.made([row, None], "grid", sink)

    assert grid[0] is row
    assert grid[1] is None


def test_the_text_of_a_list_drops_its_condition_and_its_repr_does_not() -> None:
    items, sink = tracked([1])

    assert repr(items) == "[1]"
    assert str(items) == "[1]" and f"{items}" == "[1]"
    # an f-string reads the text through `__str__` and then `__format__`, as for a tracked int
    assert downgrades(sink) == ["__str__", "__str__", "__format__"]


def test_a_pickle_holds_the_plain_list() -> None:
    items, sink = tracked([1, 2])

    loaded = pickle.loads(pickle.dumps(items))

    assert loaded == [1, 2] and type(loaded) is list
    assert all(type(item) is int for item in loaded)
    assert downgrades(sink) == ["__reduce_ex__"]


def test_a_list_goes_plain_once_and_is_named_once() -> None:
    items, sink = tracked([1, 2])

    items.lose("sort")

    # plain from then on: its items are plain values, and nothing more is recorded
    assert type(items[0]) is int and bool(items) and 1 in items
    assert downgrades(sink) == ["sort"] and forks(sink) == []


def test_a_plain_list_answers_as_pythons_own_with_nothing_recorded() -> None:
    items, sink = tracked([2, 1])

    items.lose("sort")
    copied, doubled, stepped = items.copy(), items * 2, items[::2]
    items.reverse()
    position = items.index(1, 0)

    assert (list.copy(items), copied, doubled, stepped, position) == (
        [1, 2],
        [2, 1],
        [2, 1, 2, 1],
        [2],
        0,
    )
    assert downgrades(sink) == ["sort"] and forks(sink) == []
    assert not items.holds("__len__")


def test_an_item_changed_in_place_without_the_methods_is_read_plain() -> None:
    items, sink = tracked([1, 2])

    list.__setitem__(items, 0, 5)
    first = items[0]

    assert type(first) is int and first == 5
    assert downgrades(sink) == ["__getitem__"] and items.expression is None


def test_a_slice_whose_bound_pyct_does_not_follow_is_a_downgrade() -> None:
    items, sink = tracked([1, 2, 3])

    with pytest.raises(TypeError):
        del items["a":]
    part = items[1 : ConcolicInt(5, expression="n", sink=sink) > 0]

    assert part == []
    assert downgrades(sink) == ["__getitem__"]


def test_an_item_handed_out_from_a_slot_changed_outside_the_methods_is_plain() -> None:
    items, sink = tracked([1, 2])

    list.__setitem__(items, 0, 5)
    item = handed(items, 0, 0, "__iter__")

    assert type(item) is int and item == 5
    assert downgrades(sink) == ["__iter__"]

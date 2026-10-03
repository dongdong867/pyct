"""A tracked list read: its truth test, an index, a slice, and the walks from either end."""

import heapq
import pickle
from typing import Any

import pytest

from pyct.core import bound
from pyct.core.bools import ConcolicBool
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
            items.append(ConcolicStr.made(value, expression=access, sink=sink))
        elif isinstance(value, int) and not isinstance(value, bool):
            items.append(ConcolicInt.made(value, expression=access, sink=sink))
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
    i = ConcolicInt.made(-1, expression="i", sink=sink)

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
        items[ConcolicInt.made(2, expression="i", sink=sink)]
    with pytest.raises(IndexError):
        items[ConcolicInt.made(-3, expression="j", sink=sink)]

    assert forks(sink) == [
        ([">", ["len", "items"], "i"], False),
        ([">", ["len", "items"], "j"], True),
        ([">=", ["len", "items"], ["-", "j"]], False),
    ]


def test_a_tracked_index_into_items_of_two_kinds_is_a_downgrade() -> None:
    items, sink = tracked([1, "a"])

    item = items[ConcolicInt.made(1, expression="i", sink=sink)]

    assert type(item) is str and item == "a"
    assert downgrades(sink) == ["__getitem__"] and forks(sink) == []


@pytest.mark.parametrize("changed", [False, True], ids=["the split's list", "a list made from it"])
def test_a_tracked_index_into_a_split_s_list_is_a_downgrade(changed: bool) -> None:
    sink: list[SinkItem] = []
    parts: Any = ConcolicStr.made("a,b", expression="s", sink=sink).split(",")
    if changed:
        parts = parts + ["z"]

    item = parts[ConcolicInt.made(1, expression="i", sink=sink)]

    # the solver reads a split's piece at a position the path writes, not at one it chooses
    assert type(item) is str and item == "b"
    assert downgrades(sink) == ["__getitem__"] and forks(sink) == []


@pytest.mark.parametrize(
    ("made", "marked"),
    [
        (lambda sink: ConcolicStr.made("a\nb", expression="s", sink=sink).splitlines(), True),
        (lambda sink: ConcolicStr.made("a,b", expression="s", sink=sink).split(",")[1:], True),
        (lambda sink: tracked(["a", "b"])[0], False),
    ],
    ids=["a split's list", "a slice of one", "an argument's list"],
)
def test_a_walk_over_a_split_s_list_marks_its_forks(made: Any, marked: bool) -> None:
    sink: list[SinkItem] = []
    items = made(sink)
    sink = sink or items.sink

    list(items)
    walks = [item for item in sink if isinstance(item, Branch) and item.lost_as == "__iter__"]

    # the tree aims at a split's walk forks after the path's other forks; a list argument's
    # walk keeps the order it had
    assert walks and all(branch.split_walk is marked for branch in walks), walks


def test_a_tracked_index_into_a_list_that_holds_a_piece_keeps_its_forks() -> None:
    items, sink = tracked(["q"])
    piece = ConcolicStr.made("a", expression=["[]", ["split", "s", "','"], 0], sink=sink)
    items.append(piece)

    item = items[ConcolicInt.made(0, expression="i", sink=sink)]

    # the list is the argument's, changed: only a split's own list is read at positions the
    # path writes
    assert isinstance(item, ConcolicStr)
    assert downgrades(sink) == [] and len(forks(sink)) == 2


def test_a_list_changed_many_times_is_looked_through_once_for_a_split() -> None:
    items, sink = tracked(["q"])
    for at in range(60):
        items[0] = ConcolicStr.made("x", expression=["[]", "t", at], sink=sink)

    # each change names the list before it twice, so a look that did not share the parts it
    # met would take 2**60 steps
    item = items[ConcolicInt.made(0, expression="i", sink=sink)]

    assert isinstance(item, ConcolicStr) and downgrades(sink) == []


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
    i = ConcolicInt.made(0, expression="i", sink=sink)

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
    compared = items[ConcolicInt.made(1, expression="x", sink=sink) > 0]

    # a compare's answer is a position pyct does not follow: list's own read, named, and plain
    assert type(compared) is int and compared == 2
    assert downgrades(sink) == ["__getitem__"]


def test_a_slice_is_a_tracked_list_that_records_no_fork() -> None:
    items, sink = tracked([1, 2, 3, 4])
    n = ConcolicInt.made(1, expression="n", sink=sink)

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
    tracked_step = items[:: ConcolicInt.made(2, expression="k", sink=sink)]

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


def test_pyct_s_len_is_the_list_s_length_term() -> None:
    items, sink = tracked([1, 2])
    items.append(3)

    size = bound.len(items)

    # a length cannot fail, so reading one records nothing
    assert downgrades(sink) == [] and forks(sink) == []
    assert isinstance(size, ConcolicInt) and int.__int__(size) == 3
    assert size.expression == ["len", ["+", "items", ["[,]", 3]]]


def test_pyct_s_len_of_a_list_whose_form_stopped_describing_it_is_plain() -> None:
    items, sink = tracked([1, 2])
    list.append(items, 3)

    size = bound.len(items)

    assert type(size) is int and size == 3
    # the list turned plain here, so the line names the call that found it changed
    assert downgrades(sink) == ["__len__"]
    assert type(bound.len(items)) is int and downgrades(sink) == ["__len__"]


@pytest.mark.parametrize(("start", "filled"), [([], False), ([1], True)])
def test_pyct_s_bool_is_the_truth_test_untested(start: list[int], filled: bool) -> None:
    items, sink = tracked(start)

    truth = bound.bool_(items)

    # the condition `if items:` tests, recorded only where the target tests it
    assert isinstance(truth, ConcolicBool) and int.__bool__(truth) is filled
    assert truth.expression == ["!=", ["len", "items"], 0]
    assert forks(sink) == [] and downgrades(sink) == []
    assert bool(truth) is filled
    assert forks(sink) == [(["!=", ["len", "items"], 0], filled)]


def test_pyct_s_bool_keeps_the_form_the_list_had_at_the_call() -> None:
    items, sink = tracked([])
    items.append(0)

    truth = bound.bool_(items)
    items.append(1)

    assert truth.expression == ["!=", ["len", ["+", "items", ["[,]", 0]]], 0]
    assert int.__bool__(truth) is True and forks(sink) == []


def test_pyct_s_bool_of_a_list_whose_form_stopped_describing_it_is_plain() -> None:
    items, sink = tracked([])
    heapq.heappush(items, 0)

    truth = bound.bool_(items)

    assert truth is True
    assert downgrades(sink) == ["__bool__"] and forks(sink) == []
    assert bound.bool_(items) is True and downgrades(sink) == ["__bool__"]


def test_pyct_s_bool_through_map_is_each_list_s_truth() -> None:
    sink: list[SinkItem] = []
    rows = [ConcolicList.made([], ["[]", "grid", at], sink) for at in range(2)]

    truths = list(bound.map_(bool, rows))

    assert [truth.expression for truth in truths] == [
        ["!=", ["len", ["[]", "grid", at]], 0] for at in range(2)
    ]
    assert forks(sink) == []


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
    part = items[1 : ConcolicInt.made(5, expression="n", sink=sink) > 0]

    assert part == []
    assert downgrades(sink) == ["__getitem__"]


def test_an_item_handed_out_from_a_slot_changed_outside_the_methods_is_plain() -> None:
    items, sink = tracked([1, 2])

    list.__setitem__(items, 0, 5)
    item = handed(items, 0, 0, "__iter__")

    assert type(item) is int and item == 5
    assert downgrades(sink) == ["__iter__"]

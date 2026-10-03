"""Each tracked list, string and dict's length range: how a change moves it, which forks narrow
it, which checks it decides, and the range the int `len(x)` carries."""

from typing import Any

import pytest

from pyct.core import bound
from pyct.core.bools import ConcolicBool
from pyct.core.branch import Branch, Expression, Fact, SinkItem
from pyct.core.ints import ConcolicInt
from pyct.core.lists import ConcolicList
from pyct.core.spans import UNKNOWN, Span
from pyct.core.strs import ConcolicStr
from tests.unit.core.test_dicts import tracked as tracked_dict
from tests.unit.core.test_list_reads import decided, forks, tracked


def length_of(value: object) -> ConcolicInt:
    measured = bound.len(value)
    assert isinstance(measured, ConcolicInt)
    return measured


def span_of(value: object) -> Span:
    """The range a tracked list or string keeps, narrowed so a comparison means something."""
    assert isinstance(value, ConcolicStr | ConcolicList), value
    return value.span


def text(value: str, name: str = "s") -> tuple[ConcolicStr, list[SinkItem]]:
    sink: list[SinkItem] = []
    return ConcolicStr.made(value, expression=name, sink=sink), sink


# each change a list's own methods make, and the range it leaves a list of 2 or 3 items
CHANGES: list[tuple[str, Any, tuple[int, int | None]]] = [
    ("append", lambda xs: xs.append(9), (3, 4)),
    ("insert", lambda xs: xs.insert(0, 9), (3, 4)),
    ("pop", lambda xs: xs.pop(), (1, 2)),
    ("pop at", lambda xs: xs.pop(0), (1, 2)),
    ("remove", lambda xs: xs.remove(1), (1, 2)),
    ("del", lambda xs: xs.__delitem__(0), (1, 2)),
    ("del slice", lambda xs: xs.__delitem__(slice(1, None)), (1, 1)),
    ("store", lambda xs: xs.__setitem__(0, 9), (2, 3)),
    ("slice store", lambda xs: xs.__setitem__(slice(0, 1), [7, 8, 9]), (4, 5)),
    ("extend", lambda xs: xs.extend([7, 8]), (4, 5)),
    ("+=", lambda xs: xs.__iadd__([7]), (3, 4)),
    ("*=", lambda xs: xs.__imul__(2), (4, 6)),
    ("reverse", lambda xs: xs.reverse(), (2, 3)),
]


@pytest.mark.parametrize(("name", "change", "after"), CHANGES, ids=[c[0] for c in CHANGES])
def test_a_change_moves_the_range_as_it_moves_the_length(
    name: str, change: Any, after: Any
) -> None:
    items, _ = tracked([1, 2])
    # a fork on its length leaves the list two or three items long
    assert items.measure(">", 1, True) and not items.measure(">", 3, False)
    assert items.span == (2, 3)

    change(items)

    assert items.span == after


def test_a_sort_leaves_a_display_of_as_many_items_as_its_walk_took() -> None:
    items, _ = tracked([3, 1])

    items.sort()

    assert items.span == (2, 2)


def test_a_slice_with_a_tracked_bound_marks_the_list_and_each_change_starts_it_over() -> None:
    items, sink = tracked([1, 2, 3])
    n = ConcolicInt.made(1, "n", sink)
    list(items)

    del items[n:]
    items.append(0)

    assert items.marked and items.span == UNKNOWN
    assert bool(items) and forks(sink)[-1] == (["!=", ["len", items.expression], 0], True)


def test_lists_made_from_a_list_carry_its_range_and_its_mark() -> None:
    items, sink = tracked([1, 2])
    list(items)
    n = ConcolicInt.made(0, "n", sink)

    assert items.copy().span == (2, 2) and items[:].span == (2, 2)
    assert (items + [0]).span == (3, 3) and ([0] + items).span == (3, 3)
    assert (items * 2).span == (4, 4) and items[1:].span == (1, 1)
    # a tracked bound may cut another number of items on another input
    assert items[n:].span == UNKNOWN
    items[n:n] = []
    assert items.marked and items.copy().marked


def test_a_row_read_again_under_another_name_starts_with_no_range() -> None:
    sink: list[SinkItem] = []
    rows: list[object] = [ConcolicList.made([], ["[]", "grid", at], sink) for at in range(2)]
    grid = ConcolicList.made(rows, "grid", sink)
    grid.__dict__["shadow"] = list(rows)
    grid.__dict__["kinds"] = frozenset({"list"})
    i = ConcolicInt.made(0, "i", sink)

    assert not grid[0]
    row = grid[i]

    assert isinstance(row, ConcolicList) and row.expression == ["[]", "grid", "i"]
    assert row.span == UNKNOWN
    assert not row and forks(sink)[-1] == (["!=", ["len", ["[]", "grid", "i"]], 0], False)


def test_a_list_kept_from_an_earlier_call_knows_nothing_of_this_path() -> None:
    items, _ = tracked([1, 2])
    list(items)
    kept, _ = tracked([1], name="kept")
    list(kept)

    assert items.span_of(kept) == UNKNOWN
    assert items.span_of(items) == (2, 2) and items.span_of([0, 0, 0]) == (3, 3)


def test_a_list_s_walks_truth_tests_indexes_and_compares_are_decided_by_its_range() -> None:
    items, sink = tracked([1, 2])
    list(items)

    assert items and items[1] == 2 and items[-2] == 1
    assert items != [1] and list(reversed(items)) == [2, 1]
    assert items.pop() == 2

    # only the first walk's three forks are on the length; every later check is decided
    measured = [check for check, _ in forks(sink) if ["len", "items"] in check]  # type: ignore[operator]
    assert len(measured) == 3
    assert [check for check, _ in decided(sink)] == [
        ["!=", ["len", "items"], 0],
        [">", ["len", "items"], 1],
        [">=", ["len", "items"], 2],
        ["==", ["len", "items"], 1],
        *([">", ["len", "items"], at] for at in range(3)),
        ["!=", ["len", "items"], 0],
    ]


def test_a_list_compare_s_run_out_answer_is_decided_where_both_ranges_prove_it() -> None:
    items, sink = tracked([5])
    list(items)

    shorter = items < [5, 0]

    assert isinstance(shorter, ConcolicBool) and shorter.decided
    assert bool(shorter) and isinstance(sink[-1], Fact)


def test_a_string_s_range_follows_its_pieces_and_its_walks() -> None:
    s, sink = text("ab")

    assert span_of(s + "!") == (1, None) and span_of("!" + s) == (1, None)
    assert span_of(s[1:]) == UNKNOWN
    assert span_of(s[0]) == (1, 1) and span_of(next(iter(s))) == (1, 1)
    list(s)
    assert s.span == (2, 2)
    assert span_of(s + s) == (4, 4) and span_of(s[1:]) == (1, 1) and span_of(s[::-1]) == (2, 2)
    walked, known = len(forks(sink)), len(decided(sink))

    list(s)

    # the second walk's two passes and its end are facts
    assert len(forks(sink)) == walked and len(decided(sink)) == known + 3


def test_a_string_s_truth_test_and_index_stay_forks_and_narrow_its_range() -> None:
    s, sink = text("ab")

    assert s and s[1] == "b"

    assert s.span == (2, None)
    assert [check for check, _ in forks(sink)][:2] == [["!=", "s", "''"], [">", ["len", "s"], 1]]
    list(s)
    assert [check for check, _ in decided(sink)] == [[">", ["len", "s"], 0], [">", ["len", "s"], 1]]


def test_a_dict_s_second_walk_and_truth_test_are_decided_by_its_first() -> None:
    config, sink = tracked_dict({"a": 1})
    list(config)
    walked = len(forks(sink))

    assert list(config) == ["a"] and config and len(forks(sink)) == walked
    assert (["!=", ["len", "config"], 0], True) in decided(sink)
    assert ([">", ["len", "config"], 1], False) in decided(sink)


def test_a_dict_s_range_moves_with_a_change_and_starts_over_after_a_forkless_one() -> None:
    config, sink = tracked_dict({"a": 1})
    list(config)
    config["b"] = 2

    assert config.measured() == (2, 2)
    config[ConcolicStr.made("pyct1", "n", sink)] = 3

    assert config.span == UNKNOWN and config.measured() == (1, None)


def test_a_lookup_in_a_dict_whose_range_holds_no_key_is_a_fact() -> None:
    config, sink = tracked_dict({})
    list(config)

    assert "a" not in config

    assert decided(sink)[-1] == (["in", "'a'", "config"], False)


# each compare of `len(xs)` a range of exactly two decides, with a plain int, through plain
# arithmetic on either side
PROVEN: list[Any] = [
    lambda n: n > 1,
    lambda n: n > 3,
    lambda n: n - 1 > 3,
    lambda n: n * 2 == 4,
    lambda n: 2 + n <= 4,
    lambda n: 5 - n >= 3,
    lambda n: n * -1 < 0,
]


@pytest.mark.parametrize("compare", PROVEN)
def test_a_compare_of_a_measured_length_with_a_plain_int_is_a_fact(compare: Any) -> None:
    items, sink = tracked([1, 2])
    list(items)
    walked = len(forks(sink))

    answer = compare(length_of(items))
    assert isinstance(answer, ConcolicBool) and answer.decided
    bool(answer)

    assert len(forks(sink)) == walked and isinstance(sink[-1], Fact)


# compares of `len(xs)` that stay forks however the range stands
UNPROVEN: list[Any] = [
    lambda n, other: n - other > 0,
    lambda n, other: n // 2 > 0,
    lambda n, other: n % 2 == 1,
    lambda n, other: n > other,
    lambda n, other: -n < 0,
]


@pytest.mark.parametrize("compare", UNPROVEN)
def test_a_compare_through_any_other_operation_stays_a_fork(compare: Any) -> None:
    items, sink = tracked([1, 2])
    list(items)
    other = length_of(items)
    walked = len(forks(sink))

    answer = compare(length_of(items), other)
    bool(answer)

    assert len(forks(sink)) == walked + 1 and isinstance(sink[-1], Branch)


def test_len_carries_the_range_its_value_had_at_the_call() -> None:
    items, sink = tracked([1])
    before = length_of(items)
    list(items)

    assert before.span == UNKNOWN and length_of(items).span == (1, 1)
    assert not (before > 0).decided and (length_of(items) > 0).decided
    expression: Expression = length_of(items).expression
    assert expression == ["len", "items"] and len(forks(sink)) == 2

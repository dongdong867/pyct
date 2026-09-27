"""A tracked list changed: each change's form, held against Python, and the forms not followed."""

import contextlib
import copy
import random
from collections.abc import Callable
from typing import Any

import pytest

from pyct.core.branch import Branch, Downgrade, Expression
from pyct.core.ints import ConcolicInt
from pyct.core.list_state import plain
from tests.unit.core.python_forms import evaluate
from tests.unit.core.test_list_reads import downgrades, forks, tracked, values

# each change a list's own methods make, with plain int positions and values, as a target
# writes it; `x` is a tracked int the tests put in
CHANGES: dict[str, Callable[[Any, Any], object]] = {
    "append": lambda a, x: a.append(x),
    "append a literal": lambda a, x: a.append(7),
    "append a list": lambda a, x: a.append([x, "s", None, 1.5, True]),
    "extend": lambda a, x: a.extend([x, 8]),
    "extend a tuple": lambda a, x: a.extend((9, x)),
    "extend itself": lambda a, x: a.extend(a),
    "+=": lambda a, x: a.__iadd__([x]),
    "insert": lambda a, x: a.insert(1, x),
    "insert past the end": lambda a, x: a.insert(10, x),
    "insert from the end": lambda a, x: a.insert(-2, x),
    "insert at a tracked place": lambda a, x: a.insert(x, 5),
    "pop": lambda a, x: a.pop(),
    "pop at": lambda a, x: a.pop(1),
    "pop from the end": lambda a, x: a.pop(-2),
    "pop at a tracked place": lambda a, x: a.pop(x),
    "remove": lambda a, x: a.remove(2),
    "item": lambda a, x: a.__setitem__(1, x),
    "item from the end": lambda a, x: a.__setitem__(-1, 0),
    "del": lambda a, x: a.__delitem__(0),
    "del from the end": lambda a, x: a.__delitem__(-1),
    "del a slice": lambda a, x: a.__delitem__(slice(1, 3)),
    "del a backward slice": lambda a, x: a.__delitem__(slice(3, 1)),
    "del from a tracked place": lambda a, x: a.__delitem__(slice(x, None)),
    "slice": lambda a, x: a.__setitem__(slice(1, 2), [x, x]),
    "slice before the start": lambda a, x: a.__setitem__(slice(-9, 1), []),
    "slice past the end": lambda a, x: a.__setitem__(slice(None, 9), [x]),
    "reverse": lambda a, x: a.reverse(),
    "sort": lambda a, x: a.sort(),
    "sort by a key, reversed": lambda a, x: a.sort(key=lambda v: -v, reverse=True),
    "*=": lambda a, x: a.__imul__(2),
    "*= nothing": lambda a, x: a.__imul__(0),
}


def check_form(items: Any, original: list[int], x: int) -> None:
    """The list's form, evaluated by Python over the arguments, is the list it holds."""
    evaluated = evaluate(items.expression, {"items": original, "x": x})
    assert _plain(evaluated) == _plain(list.copy(items)), items.expression


def _plain(value: object) -> object:
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return plain(value)


@pytest.mark.parametrize("name", CHANGES)
def test_each_change_writes_the_form_python_builds(name: str) -> None:
    original = [1, 2, 3, 4]
    items, sink = tracked(original)
    x = ConcolicInt(1, expression="x", sink=sink)

    CHANGES[name](items, x)

    check_form(items, original, 1)
    assert downgrades(sink) == []


def test_a_long_run_of_changes_keeps_the_form_python_builds() -> None:
    """Changes in random order, each form held against Python as the target makes it.

    A list that turns plain, a tracked position into items of two kinds say, has no form left
    to hold, and says so on its line.
    """
    chooser = random.Random(7)
    held = 0
    for _ in range(300):
        original = [chooser.randrange(-3, 4) for _ in range(chooser.randrange(0, 6))]
        items, sink = tracked(original)
        x = ConcolicInt(1, expression="x", sink=sink)
        for name in chooser.sample(sorted(CHANGES), 6):
            # Python's own refusal, a pop past the end or a sort of a list and an int, changes
            # nothing
            with contextlib.suppress(IndexError, ValueError, TypeError):
                CHANGES[name](items, x)
            if items.expression is None:
                assert downgrades(sink), name
                break
            check_form(items, original, 1)
            held += 1
    assert held > 1000


def test_a_pop_hands_out_the_item_as_indexed() -> None:
    items, sink = tracked([1, 2, 3])

    last, first = items.pop(), items.pop(0)

    assert values([last, first]) == [3, 1]
    assert last.expression == ["[]", "items", -1]
    assert first.expression == ["[]", ["[:]", "items", None, -1], 0]
    assert forks(sink) == [
        (["!=", ["len", "items"], 0], True),
        ([">", ["len", ["[:]", "items", None, -1]], 0], True),
    ]


def test_a_pop_or_a_remove_that_raises_records_its_fork_and_changes_nothing() -> None:
    empty, sink = tracked([])
    one, one_sink = tracked([1])

    with pytest.raises(IndexError):
        empty.pop()
    with pytest.raises(IndexError):
        one.pop(4)
    with pytest.raises(ValueError, match="not in list"):
        one.remove(7)

    assert forks(sink) == [(["!=", ["len", "items"], 0], False)]
    assert forks(one_sink) == [
        ([">", ["len", "items"], 4], False),
        ([">", ["len", "items"], 0], True),
        (["==", ["[]", "items", 0], 7], False),
        ([">", ["len", "items"], 1], False),
    ]
    assert (empty.expression, one.expression) == ("items", "items")


def test_an_item_set_or_deleted_past_the_end_raises_after_its_fork() -> None:
    items, sink = tracked([1])

    with pytest.raises(IndexError):
        items[3] = 0
    with pytest.raises(IndexError):
        del items[-2]

    assert forks(sink) == [
        ([">", ["len", "items"], 3], False),
        ([">=", ["len", "items"], 2], False),
    ]
    assert items.expression == "items"


def test_clear_leaves_a_plain_empty_list() -> None:
    items, sink = tracked([1, 2])

    items.clear()

    assert items.expression is None and list.copy(items) == []
    assert not items and forks(sink) == []


def test_a_copy_keeps_the_form_a_deep_copy_too() -> None:
    items, sink = tracked([1, 2])

    copies = [items.copy(), copy.copy(items), copy.deepcopy(items), items[:]]

    assert all(made.expression == "items" and made is not items for made in copies)
    assert all(values(made) == [1, 2] for made in copies)
    assert downgrades(sink) == []


def test_joining_and_repeating_build_tracked_lists() -> None:
    items, sink = tracked([1, 2])
    other, _ = tracked([5], name="other")

    built = [items + [3], [0] + items, items + other, items * 2, 3 * items, items * 0]

    assert [made.expression for made in built] == [
        ["+", "items", ["[,]", 3]],
        ["+", ["[,]", 0], "items"],
        ["+", "items", "other"],
        ["*", "items", 2],
        ["*", 3, "items"],
        ["*", "items", 0],
    ]
    assert [values(made) for made in built] == [
        [1, 2, 3],
        [0, 1, 2],
        [1, 2, 5],
        [1, 2, 1, 2],
        [1, 2, 1, 2, 1, 2],
        [],
    ]
    assert downgrades(sink) == []


def test_a_list_added_to_a_value_that_is_not_a_list_raises_as_pythons_does() -> None:
    items, _ = tracked([1])

    with pytest.raises(TypeError):
        items + (1,)
    with pytest.raises(TypeError):
        (1,) + items
    with pytest.raises(TypeError):
        items * "2"


# the forms pyct does not follow: each a downgrade named by the operation, Python's own change
UNFOLLOWED: dict[str, tuple[Callable[[Any, Any], object], str]] = {
    "append an object": (lambda a, n: a.append(object()), "append"),
    "append a dict": (lambda a, n: a.append({"k": 1}), "append"),
    "extend with an object": (lambda a, n: a.extend([object()]), "extend"),
    "+= an object": (lambda a, n: a.__iadd__([object()]), "__iadd__"),
    "insert at a str": (lambda a, n: a.insert(n > 0, 5), "insert"),
    "insert an object": (lambda a, n: a.insert(0, object()), "insert"),
    "pop at a compare": (lambda a, n: a.pop(n > 0), "pop"),
    "item at a compare": (lambda a, n: a.__setitem__(n > 0, 5), "__setitem__"),
    "item an object": (lambda a, n: a.__setitem__(0, object()), "__setitem__"),
    "slice by a step": (lambda a, n: a.__setitem__(slice(None, None, 2), [0, 0]), "__setitem__"),
    "slice an object": (lambda a, n: a.__setitem__(slice(0, 1), [object()]), "__setitem__"),
    "del by a step": (lambda a, n: a.__delitem__(slice(None, None, 2)), "__delitem__"),
    "del at a compare": (lambda a, n: a.__delitem__(n > 0), "__delitem__"),
    "*= a tracked count": (lambda a, n: a.__imul__(n), "__imul__"),
    "+ an object": (lambda a, n: a + [object()], "__add__"),
    "* a tracked count": (lambda a, n: a * n, "__mul__"),
    "a tracked count *": (lambda a, n: n * a, "__rmul__"),
    "index from a start": (lambda a, n: a.index(2, 1), "index"),
}


@pytest.mark.parametrize("name", UNFOLLOWED)
def test_a_form_pyct_does_not_follow_is_a_downgrade_named_by_the_operation(name: str) -> None:
    items, sink = tracked([1, 2, 3, 4])
    n = ConcolicInt(2, expression="n", sink=sink)
    change, named = UNFOLLOWED[name]

    change(items, n)

    assert named in downgrades(sink), downgrades(sink)
    assert downgrades(sink)[-1] == named


def test_a_list_plain_after_a_change_it_could_not_follow_records_nothing_more() -> None:
    items, sink = tracked([1, 2])

    items.append(object())
    items.append(3)
    items[0] = 5
    del items[0]
    items.sort(key=id)
    items.reverse()
    items.pop()
    items.remove(3)
    items.insert(0, 1)
    items *= 1
    items += [4]

    assert items.expression is None
    assert downgrades(sink) == ["append"] and forks(sink) == []
    assert all(type(item) in (int, object) for item in list.copy(items))


def test_a_sort_with_arguments_list_does_not_take_raises_as_pythons_does() -> None:
    items, sink = tracked([2, 1])

    with pytest.raises(TypeError):
        items.sort(lambda v: v)
    with pytest.raises(TypeError):
        items.sort(cmp=None)

    assert items.expression == "items" and forks(sink) == []


def test_a_sort_records_the_walk_and_each_compare_pythons_sort_makes() -> None:
    items, sink = tracked([2, 1])

    items.sort()

    assert items.expression == ["[,]", ["[]", "items", 1], ["[]", "items", 0]]
    assert forks(sink) == [
        ([">", ["len", "items"], 0], True),
        ([">", ["len", "items"], 1], True),
        ([">", ["len", "items"], 2], False),
        (["<", ["[]", "items", 1], ["[]", "items", 0]], True),
    ]


def test_a_sort_that_raises_leaves_the_list_as_it_was() -> None:
    items, sink = tracked([1, "a"])

    with pytest.raises(TypeError):
        items.sort()

    assert values(items) == [1, "a"] and items.expression == "items"


def test_a_change_outside_the_methods_turns_the_next_change_plain() -> None:
    items, sink = tracked([1, 2])

    list.append(items, 3)
    items.append(4)

    assert items.expression is None
    assert downgrades(sink) == ["append"]
    assert values(items) == [1, 2, 3, 4]


def test_a_list_taken_in_from_another_tracked_list_plain_after_a_change_is_read_plain() -> None:
    items, sink = tracked([1])
    other, other_sink = tracked([2], name="other")

    list.append(other, 3)
    items.extend(other)

    # the other list turns plain where the extend reads it, and goes in as the values it holds
    assert other.expression is None and downgrades(other_sink) == ["extend"]
    assert items.expression == ["+", "items", ["[,]", 2, 3]]
    assert values(items) == [1, 2, 3] and downgrades(sink) == []


def test_a_walk_and_the_forks_of_a_sort_share_one_sink() -> None:
    items, sink = tracked([3, 1, 2])

    items.sort(reverse=True)

    compares = [
        item
        for item in sink
        if isinstance(item, Branch)
        and isinstance(item.expression, list)
        and item.expression[0] == "<"
    ]
    assert compares and all(isinstance(item, Branch) for item in compares)
    assert values(items) == [3, 2, 1]


def test_a_display_written_too_deep_is_a_downgrade() -> None:
    items, sink = tracked([1])
    deep: list[object] = []
    for _ in range(100):
        deep = [deep]

    items.append(deep)

    assert downgrades(sink) == ["append"] and items.expression is None


def test_a_display_that_holds_itself_is_a_downgrade() -> None:
    items, sink = tracked([1])
    loop: list[object] = []
    loop.append(loop)

    items.append(loop)

    assert downgrades(sink) == ["append"]


def test_an_item_set_writes_a_tracked_list_by_its_form() -> None:
    items, sink = tracked([1, 2])
    other, _ = tracked([5], name="other")

    items[0] = other

    written: Expression = ["[,]", "other"]
    assert items.expression == [
        "+",
        ["+", ["[:]", "items", None, 0], written],
        ["[:]", ["[:]", "items", 0, None], 1, None],
    ]
    assert isinstance(sink, list) and not [item for item in sink if isinstance(item, Downgrade)]

"""An index read and a `get` on a plain dict with a tracked key: one `==` fork per key, in the
dict's order, until one holds. An index read on a plain list, tuple or str with a tracked int."""

from collections import defaultdict

import pytest

from pyct.core.dicts.dicts import ConcolicDict
from pyct.core.entry.lookups import item, routed
from pyct.core.foundation.branch import SinkItem
from pyct.core.lists.lists import ConcolicList
from pyct.core.numbers.bools import ConcolicBool
from pyct.core.numbers.floats import ConcolicFloat
from pyct.core.numbers.ints import ConcolicInt
from pyct.core.strs.strs import ConcolicStr
from tests.unit.core.entry.test_substitutes import expressions

METAS = {"US": 1, "FR": 33, "DE": 49}
CODES = [10, 20, 30, 40]
ALPHA = "abcdefghijklmnopqrstuvwxyz"


def text(value: str, sink: list[SinkItem]) -> ConcolicStr:
    return ConcolicStr.made(value, expression="s", sink=sink)


def number(value: int, sink: list[SinkItem]) -> ConcolicInt:
    return ConcolicInt.made(value, expression="n", sink=sink)


def tried(*keys: str, found: str | None = None) -> list[object]:
    """The forks of a search that passes each key and, when `found` is given, stops there."""
    forks: list[object] = [(["==", "s", f"'{key}'"], False) for key in keys]
    if found is not None:
        forks.append((["==", "s", f"'{found}'"], True))
    return forks


def test_a_tracked_key_forks_on_each_key_until_one_holds() -> None:
    sink: list[SinkItem] = []

    assert item(METAS, text("FR", sink)) == 33
    assert expressions(sink) == tried("US", found="FR")


@pytest.mark.parametrize(
    ("kind", "value", "table"),
    [
        (ConcolicInt, 7, {3: "a", 7: "b"}),
        (ConcolicBool, True, {0: "a", 1: "b"}),
        (ConcolicFloat, 1.0, {0: "a", 1: "b"}),
    ],
)
def test_a_tracked_int_bool_or_float_key_forks_on_each_key_until_one_holds(
    kind: type[ConcolicInt | ConcolicBool | ConcolicFloat], value: object, table: dict[int, str]
) -> None:
    first, second = table
    for read in (lambda key: item(table, key), lambda key: routed(table.get)(key)):
        sink: list[SinkItem] = []

        assert read(kind.made(value, expression="k", sink=sink)) == table[value]
        assert expressions(sink) == [(["==", "k", first], False), (["==", "k", second], True)]


def test_a_miss_records_one_fork_per_key_in_the_dict_s_order() -> None:
    sink: list[SinkItem] = []

    with pytest.raises(KeyError):
        item(METAS, text("XX", sink))
    assert expressions(sink) == tried("US", "FR", "DE")


def test_a_miss_raises_the_key_error_plain_python_gives() -> None:
    with pytest.raises(KeyError) as plain:
        METAS["XX"]
    with pytest.raises(KeyError) as tracked:
        item(METAS, text("XX", []))

    assert str(tracked.value) == str(plain.value)


def test_get_answers_none_or_its_default_on_a_miss() -> None:
    sink: list[SinkItem] = []
    get = routed(METAS.get)

    assert get(text("XX", sink)) is None
    assert get(text("XX", sink), 7) == 7
    assert expressions(sink) == tried("US", "FR", "DE") * 2


def counted(*items: int, found: int | None = None, from_start: bool = True) -> list[object]:
    """The forks of a chain that passes each item's position and, when `found` is given, stops
    there: `n >= 0` first, then `n == i` for each position, or `n == -i` counted from the end."""
    forks: list[object] = [([">=", "n", 0], from_start)]
    forks += [(["==", "n", at], False) for at in items]
    if found is not None:
        forks.append((["==", "n", found], True))
    return forks


def test_a_tracked_index_forks_on_each_item_until_one_holds() -> None:
    for container in (CODES, tuple(CODES)):
        sink: list[SinkItem] = []

        assert item(container, number(2, sink)) == 30
        assert expressions(sink) == counted(0, 1, found=2)


def test_a_negative_index_counts_from_the_end() -> None:
    sink: list[SinkItem] = []

    assert item(CODES, number(-1, sink)) == 40
    assert expressions(sink) == counted(found=-1, from_start=False)
    sink.clear()
    assert item(CODES, number(-3, sink)) == 20
    assert expressions(sink) == counted(-1, -2, found=-3, from_start=False)


@pytest.mark.parametrize(
    ("index", "forks"),
    [
        (4, counted(0, 1, 2, 3)),
        (-5, counted(-1, -2, -3, -4, from_start=False)),
    ],
)
def test_an_index_past_either_end_raises_index_error_as_python_does(
    index: int, forks: list[object]
) -> None:
    sink: list[SinkItem] = []
    with pytest.raises(IndexError) as plain:
        CODES[index]

    with pytest.raises(IndexError) as tracked:
        item(CODES, number(index, sink))

    assert str(tracked.value) == str(plain.value)
    assert expressions(sink) == forks


def test_a_tracked_int_into_a_plain_str_is_a_tracked_character() -> None:
    sink: list[SinkItem] = []

    character = item(ALPHA, number(16, sink))

    assert isinstance(character, ConcolicStr)
    assert character.expression == ["[]", f"'{ALPHA}'", "n"]
    assert str.__str__(character) == "q"
    assert expressions(sink) == [
        ([">", ["len", f"'{ALPHA}'"], "n"], True),
        ([">=", ["len", f"'{ALPHA}'"], ["-", "n"]], True),
    ]


def test_three_hundred_keys_are_searched_and_three_hundred_one_are_not() -> None:
    searched = {f"k{n}": n for n in range(300)}
    past = {f"k{n}": n for n in range(301)}
    sink: list[SinkItem] = []

    assert item(searched, text("k299", sink)) == 299
    assert expressions(sink) == tried(*(f"k{n}" for n in range(299)), found="k299")
    sink.clear()
    assert item(past, text("k300", sink)) == 300
    assert expressions(sink) == [(["==", "s", "'k300'"], True), "__getitem__"]
    sink.clear()
    assert routed(past.get)(text("k300", sink)) == 300
    assert expressions(sink) == [(["==", "s", "'k300'"], True), "get"]
    sink.clear()
    assert item(list(range(301)), number(300, sink)) == 300
    assert expressions(sink) == ["__getitem__"]


class Odd(str):
    def __eq__(self, other: object) -> bool:
        return True

    __hash__ = str.__hash__


def test_a_key_pyct_does_not_compare_is_python_s_own_and_a_downgrade() -> None:
    for table in ({(1, 2): 5, "a": 1}, {Odd("b"): 5, "a": 1}):
        sink: list[SinkItem] = []

        assert item(table, text("a", sink)) == 1
        assert expressions(sink) == [(["==", "s", "'a'"], True), "__getitem__"]
        sink.clear()
        assert routed(table.get)(text("a", sink)) == 1
        assert expressions(sink) == [(["==", "s", "'a'"], True), "get"]


def test_a_plain_key_is_python_s_own_read() -> None:
    assert item(METAS, "FR") == METAS["FR"]
    assert item(CODES, 2) == CODES[2]
    assert item(ALPHA, 3) == ALPHA[3]
    assert routed(METAS.get)("FR") == 33
    for container, key in ((METAS, "XX"), (CODES, 9), (CODES, "a"), (ALPHA, 99)):
        with pytest.raises((KeyError, IndexError, TypeError)) as plain:
            container[key]  # pyrefly: ignore[bad-index]
        with pytest.raises(type(plain.value)) as read:
            item(container, key)
        assert str(read.value) == str(plain.value)


def test_a_tracked_container_keeps_its_own_rules() -> None:
    sink: list[SinkItem] = []
    items = ConcolicList.made([4, 5], "items", sink)
    table = ConcolicDict.made({"k": 1}, "d", sink)

    assert item(items, number(1, sink)) == 5
    assert item(table, text("k", sink)) == 1
    own = expressions(sink)
    sink.clear()
    assert items[number(1, sink)] == 5
    assert table[text("k", sink)] == 1
    assert expressions(sink) == own[-len(expressions(sink)) :]
    with pytest.raises(IndexError) as plain:
        items[number(7, [])]
    with pytest.raises(IndexError) as read:
        item(items, number(7, []))
    assert str(read.value) == str(plain.value)


class Logged(dict[str, int]):
    def __init__(self, values: dict[str, int]) -> None:
        super().__init__(values)
        self.seen: list[object] = []

    def __getitem__(self, key: str) -> int:
        self.seen.append(key)
        return dict.__getitem__(self, key)


def test_a_subclass_s_own_getitem_runs_once_with_the_tracked_key() -> None:
    table = Logged(METAS)
    key = text("FR", [])

    assert item(table, key) == 33
    assert len(table.seen) == 1 and table.seen[0] is key
    with pytest.raises(KeyError):
        item(table, text("XX", []))
    assert len(table.seen) == 2


def test_a_default_dict_s_factory_runs_once_on_a_miss() -> None:
    made: list[int] = []

    def factory() -> int:
        made.append(1)
        return 9

    table = defaultdict(factory, METAS)
    sink: list[SinkItem] = []

    assert item(table, text("XX", sink)) == 9
    assert made == [1]
    assert expressions(sink) == tried("US", "FR", "DE")
    assert item(table, text("FR", [])) == 33
    assert made == [1]

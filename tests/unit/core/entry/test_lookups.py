"""An index read and a `get` on a plain dict with a tracked key: one `==` fork per key, in the
dict's order, until one holds. An index read on a plain list, tuple or str with a tracked int."""

import pytest

from pyct.core.entry.lookups import item, routed
from pyct.core.foundation.branch import SinkItem
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

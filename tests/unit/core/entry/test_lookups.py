"""An index read and a `get` on a plain dict with a tracked key: one `==` fork per key, in the
dict's order, until one holds."""

import pytest

from pyct.core.entry.lookups import item, routed
from pyct.core.foundation.branch import SinkItem
from pyct.core.numbers.ints import ConcolicInt
from pyct.core.strs.strs import ConcolicStr
from tests.unit.core.entry.test_substitutes import expressions

METAS = {"US": 1, "FR": 33, "DE": 49}


def text(value: str, sink: list[SinkItem]) -> ConcolicStr:
    return ConcolicStr.made(value, expression="s", sink=sink)


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


def test_a_tracked_int_key_forks_as_a_str_key_does() -> None:
    sink: list[SinkItem] = []
    n = ConcolicInt.made(7, expression="n", sink=sink)

    assert item({3: "a", 7: "b", 9: "c"}, n) == "b"
    assert expressions(sink) == [(["==", "n", 3], False), (["==", "n", 7], True)]


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


def test_get_answers_the_value_found_and_stops_at_its_key() -> None:
    sink: list[SinkItem] = []
    get = routed(METAS.get)

    assert get(text("DE", sink)) == 49
    assert get(text("FR", sink), 7) == 33
    assert expressions(sink) == tried("US", "FR", found="DE") + tried("US", found="FR")

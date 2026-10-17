"""A fixed-count unpack in core: a split's list records its count against the number of places
before Python unpacks it, and every value comes back as it was handed over."""

from typing import Any

import pytest

from pyct.core import substitutes
from pyct.core.branch import Branch, Fact, SinkItem
from pyct.core.strs import ConcolicStr
from tests.unit.core.test_list_reads import tracked

SPLIT = ["split", "s", "','"]


def _split(text: str, sink: list[SinkItem]) -> Any:
    parts = ConcolicStr.made(text, expression="s", sink=sink).split(",")
    sink.clear()
    return parts


@pytest.mark.parametrize(
    ("text", "unpack", "number", "expected"),
    [
        ("a,b", substitutes.unpack, 2, [(["==", ["len", SPLIT], 2], True)]),
        ("a", substitutes.unpack, 2, [(["==", ["len", SPLIT], 2], False)]),
        ("a,b,c", substitutes.unpack, 2, [(["==", ["len", SPLIT], 2], False)]),
        ("a", substitutes.unpack_starred, 2, [([">=", ["len", SPLIT], 2], False)]),
        # where the places other than the star are there, whether the starred list is empty
        (
            "a,b",
            substitutes.unpack_starred,
            2,
            [([">=", ["len", SPLIT], 2], True), ([">", ["len", SPLIT], 2], False)],
        ),
        (
            "a,b,c",
            substitutes.unpack_starred,
            2,
            [([">=", ["len", SPLIT], 2], True), ([">", ["len", SPLIT], 2], True)],
        ),
    ],
)
def test_a_split_s_list_records_its_count_before_it_unpacks(
    text: str, unpack: Any, number: int, expected: list[tuple[list[object], bool]]
) -> None:
    sink: list[SinkItem] = []
    parts = _split(text, sink)

    handed = unpack(parts, number)

    # Python is handed the same items as a plain list, which it counts in its error as it counts
    # plain Python's list; read by identity, since a compare of the pieces would record forks
    assert type(handed) is list
    assert all(mine is theirs for mine, theirs in zip(handed, list.copy(parts), strict=True))
    forks = [fork for fork in sink if isinstance(fork, Branch)]
    assert forks == sink
    assert [(fork.expression, fork.taken) for fork in forks] == expected
    # each check is the unpack's own, as a check made before Python may raise
    assert all(fork.raising for fork in forks)


def test_a_count_the_path_decided_is_a_fact() -> None:
    sink: list[SinkItem] = []
    parts = _split("a,b", sink)
    substitutes.unpack(parts, 2)
    substitutes.unpack(parts, 2)

    # the first unpack's check narrows the range to two pieces, so the second's is a fact
    assert [type(item) for item in sink] == [Branch, Fact], sink


def test_a_star_with_no_other_place_holds_on_every_split() -> None:
    sink: list[SinkItem] = []
    parts = _split("a", sink)

    substitutes.unpack_starred(parts, 0)

    # a split on a separator holds a first piece, so the starred list is never empty either
    assert [type(item) for item in sink] == [Fact, Fact], sink


@pytest.mark.parametrize(
    "value",
    [
        (1, 2),
        [1, 2],
        "ab",
        5,
        None,
        iter([1, 2]),
        ConcolicStr.made("ab", expression="s", sink=[]),
    ],
    ids=["a tuple", "a list", "a str", "an int", "None", "an iterator", "a tracked str"],
)
def test_any_other_value_comes_back_as_it_was(value: object) -> None:
    assert substitutes.unpack(value, 2) is value
    assert substitutes.unpack_starred(value, 1) is value


def test_an_argument_s_list_records_nothing_more() -> None:
    items, sink = tracked([1, 2])

    assert substitutes.unpack(items, 2) is items

    # its own walk, as Python unpacks it, records its forks as before
    assert sink == []


def test_a_split_s_list_changed_without_its_methods_records_nothing() -> None:
    sink: list[SinkItem] = []
    parts = _split("a,b", sink)
    list.append(parts, "c")

    handed = substitutes.unpack(parts, 2)

    # nothing reads the stale form, and no loss is named before the target's own read
    assert sink == []
    assert type(handed) is list and len(handed) == 3

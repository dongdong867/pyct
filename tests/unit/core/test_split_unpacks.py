"""A fixed-count unpack in core: a split's list records its count against the number of places
before Python unpacks it, and every value comes back as it was handed over."""

from typing import Any

import pytest

from pyct.core import substitutes
from pyct.core.branch import Branch, Fact, SinkItem
from pyct.core.strs import ConcolicStr
from tests.unit.core.test_dicts import tracked as tracked_dict
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


@pytest.mark.parametrize(
    ("values", "walked"),
    [([1, 2], [True, True, False]), ([1, 2, 3], [True, True, True]), ([1], [True, False])],
    ids=["as many", "one more", "one fewer"],
)
def test_an_argument_s_list_is_walked_as_python_unpacks_it(
    values: list[int], walked: list[bool]
) -> None:
    items, sink = tracked(values)

    handed = substitutes.unpack(items, 2)

    # the walk Python's unpack makes, at most one item past the places, and no count compare
    checks = [[">", ["len", "items"], at] for at in range(len(walked))]
    assert [(fork.expression, fork.taken) for fork in sink if isinstance(fork, Branch)] == [
        *zip(checks, walked, strict=True)
    ]
    # Python gets a plain list as long as the argument, which it counts in its own error
    assert type(handed) is list and len(handed) == len(values)
    # the items the walk hands out, each named by its place
    assert all(
        getattr(item, "expression", None) == ["[]", "items", at] for at, item in enumerate(handed)
    )


def test_a_starred_unpack_of_an_argument_s_list_is_python_s() -> None:
    items, sink = tracked([1, 2, 3])

    assert substitutes.unpack_starred(items, 1) is items
    assert sink == []


def test_an_argument_s_dict_is_walked_as_python_unpacks_it() -> None:
    config, sink = tracked_dict({"a": 1, "b": 2, "c": 3})

    handed = substitutes.unpack(config, 2)

    assert type(handed) is list and handed == ["a", "b", "c"]
    expressions = [fork.expression for fork in sink if isinstance(fork, Branch)]
    assert expressions == [[">", ["len", "config"], at] for at in range(3)]


def test_a_split_s_list_changed_without_its_methods_records_nothing() -> None:
    sink: list[SinkItem] = []
    parts = _split("a,b", sink)
    list.append(parts, "c")

    handed = substitutes.unpack(parts, 2)

    # nothing reads the stale form, and no loss is named before the target's own read
    assert sink == []
    assert type(handed) is list and len(handed) == 3

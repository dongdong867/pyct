"""A tracked dict's lookups after a walk: a key the walk handed out is looked up with no fork,
and a key Python shares with the target's literals is looked up after a fact of the walk's
place."""

from typing import Any

import pytest

from pyct.core.branch import Branch, Fact
from pyct.core.dicts import ConcolicDict
from pyct.core.ints import ConcolicInt
from pyct.core.strs import ConcolicStr
from tests.unit.core.test_dicts import forks, tracked


def test_a_lookup_of_a_key_a_walk_handed_out_records_no_fork() -> None:
    # every input that walks to a key looks that same key up, so no input takes the other side,
    # however long after the walk the lookup runs
    config, sink = tracked({"alpha": 1, "beta": 2})

    assert [config[key] for key in config] == [1, 2]
    assert [config.get(key) for key in reversed(config)] == [2, 1]
    assert [config[key] for key in sorted(config)] == [1, 2]
    assert [config[key] for key in list(config.keys())] == [1, 2]

    assert [part for part, _ in forks(sink) if isinstance(part, list) and part[0] == "in"] == []


def test_a_key_python_shares_records_its_lookup_given_the_walk_s_place() -> None:
    # "a" and 7 are the objects every literal "a" and 7 are, so no copy stands for them
    config, sink = tracked({"a": 1, "bb": 2})
    numbers = ConcolicDict.made({7: 1, 1_000: 2}, "numbers", sink)

    for key in config:
        config[key]
    for key in numbers:
        numbers[key]

    # each lookup's fork comes right after the fact of the place the walk read its key at
    given = [
        before.place
        for before, item in zip(sink, sink[1:], strict=False)
        if isinstance(item, Branch) and isinstance(item.expression, list)
        if item.expression[0] == "in" and isinstance(before, Fact)
    ]
    assert given == [
        ["given", ["walked", "config", "'a'"]],
        ["given", ["walked", "numbers", 7]],
    ]


@pytest.mark.parametrize(
    "merge",
    [dict, lambda c: {**c}, lambda c: {}.update(c), lambda c: {"z": 0} | dict(c)],
    ids=["dict", "unpacked", "update", "merged"],
)
def test_python_s_own_merge_looks_up_what_it_walked_with_no_fork(merge: Any) -> None:
    config, sink = tracked({"alpha": 1, "beta": 2})

    merge(config)

    assert [part for part, _ in forks(sink) if isinstance(part, list) and part[0] == "in"] == []
    assert len(forks(sink)) == 3


def test_a_literal_lookup_after_a_walk_records_its_fork() -> None:
    config, sink = tracked({"alpha": 1})

    for _ in config:
        pass
    looked = "".join(["al", "pha"])  # the target's own text, not the key the walk handed out
    assert looked in config

    assert forks(sink)[-1] == (["in", "'alpha'", "config"], True)


def test_a_tracked_key_looked_up_after_a_walk_records_only_its_lookup() -> None:
    # Python's own lookup of a tracked key compares it with a stored key of the same hash; the
    # walk's copies are plain keys, so a tracked one is never compared with them
    config, sink = tracked({"ab": 1})
    numbers = ConcolicDict.made({1000: 1, 2000: 2}, "numbers", sink)
    name = ConcolicStr.made("ab", "name", sink)
    n = ConcolicInt.made(1000, "n", sink)

    for _ in config:
        pass
    for _ in numbers:
        pass
    del sink[:]
    assert name in config and n in numbers

    assert forks(sink) == [(["in", "name", "config"], True), (["in", "n", "numbers"], True)]


def test_popitem_hands_out_the_key_a_walk_handed_out() -> None:
    # as in plain Python, where both are the one stored key object
    config, _ = tracked({"ab": 1, "cd": 2})

    walked = list(config)
    popped, _ = config.popitem()

    assert walked[-1] is popped

"""A tracked dict's lookups after a walk: a key the walk handed out is looked up with no fork,
and a key Python shares with the target's literals is looked up given the walk's place."""

from typing import Any

import pytest

from pyct.core.branch import Branch
from pyct.core.dicts import ConcolicDict
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

    lookups = [
        item.holds
        for item in sink
        if isinstance(item, Branch) and isinstance(item.expression, list)
        if item.expression[0] == "in"
    ]
    assert lookups == [
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

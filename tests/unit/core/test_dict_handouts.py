"""What a walk hands out after a change under a tracked key, and what a lookup of it asks: a
copy a change made stale, a key Python shares, and a popitem beside a tracked change."""

import json

from pyct.core.branch import Expression, Fact
from pyct.core.list_state import plain
from pyct.core.strs import ConcolicStr
from tests.unit.core.test_dicts import (
    decided,
    downgrades,
    forks,
    hold_against_python,
    tracked,
)


def part(expression: Expression, at: int) -> Expression:
    """One part of an expression that is a list, None for a leaf."""
    return expression[at] if isinstance(expression, list) else None


def test_a_store_over_a_held_key_asks_again_for_a_walked_key_given_its_place() -> None:
    config, sink = tracked({"x1": 1, "x2": 2})
    name = ConcolicStr.made("x1", "name", sink)
    keys = list(config)

    config[name] = 0
    assert [key in config for key in keys] == [True, True]

    # the store may be over either key, so the lookup asks whether it is, once n is "x1" for
    # both; the walk read each key in the argument, which its place, given before, says holds
    assert [fork for fork in forks(sink) if part(fork[0], 0) == "=="] == [
        (["==", "name", "'x1'"], True)
    ]
    assert decided(sink)[-1] == (["in", "'x2'", "config"], True)
    given = [item.place for item in sink if isinstance(item, Fact)]
    assert ["given", ["walked", "config", "'x1'"]] in given
    assert ["given", ["walked", "config", "'x2'"]] in given
    hold_against_python(sink, {"config": {"x1": 1, "x2": 2}, "name": "x1"})


def test_a_store_of_a_new_key_keeps_a_walked_key_proven() -> None:
    config, sink = tracked({"x1": 1, "x2": 2})
    name = ConcolicStr.made("a", "name", sink)
    keys = list(config)

    config[name] = 0
    asked = len(forks(sink))
    assert [key in config for key in keys] == [True, True]

    # the store's fork keeps its key apart from the argument's, so the walked keys stay
    assert forks(sink)[asked:] == []
    assert forks(sink)[-1] == (["in", "name", "config"], False)


def test_popitem_after_a_tracked_change_marks_the_dict() -> None:
    config, sink = tracked({"b": 0, "a": 0, "xx": 0})
    name = ConcolicStr.made("b", "n", sink)

    config.pop(name)
    assert "a" in config
    config.popitem()
    assert "a" in config

    # which key popitem took follows n, which no fork says: with n "xx" it takes "a", so the
    # lookup after it is a fork, though the path asked it before
    assert config.unforked
    assert forks(sink)[-1] == (["in", "'a'", "config"], True)


def test_a_tracked_store_after_popitem_is_python_s() -> None:
    config, sink = tracked({"b": 0})
    name = ConcolicStr.made("a", "n", sink)

    config.popitem()
    config[name] = 0

    # popitem took the input's last key, which no fork names, so the store may be over any
    assert downgrades(sink) == ["__setitem__"]
    assert config.unforked
    derived = config.copy()
    derived[name] = 1
    assert downgrades(sink) == ["__setitem__", "__setitem__"]


def test_a_stored_key_python_shares_leaves_its_tracked_key_free_where_a_walk_hands_it_out() -> None:
    # n's own key "a" has no copy, so a lookup of what the walk handed out is a lookup of "a":
    # comparing it with n would pin n to "a". The walk follows the store, so the dict runs as
    # v2 runs it from then on
    config, sink = tracked({})
    name = ConcolicStr.made("a", "name", sink)

    config[name] = 0
    for key in config:
        assert key in config

    assert forks(sink) == [
        (["in", "name", "config"], False),
        ([">", ["+", ["len", "config"], 1], 1], False),
    ]
    # as where the store is Python's own: answered from what the target changed, dict marked
    assert downgrades(sink) == []
    assert config.unforked


def test_a_lookup_after_a_walk_that_followed_a_tracked_change_runs_as_on_v2() -> None:
    config, sink = tracked({"b": 1})
    name = ConcolicStr.made("zz", "name", sink)
    config[name] = 0
    list(config)
    asked = len(forks(sink))

    assert "b" in config
    assert "b" in config
    config["b"] = 2
    del config["b"]

    # the walk handed out name's own key: from then on no lookup compares a key with name, the
    # dict is marked, so each lookup is a fork, no fact, and the removal reads the store before
    assert forks(sink)[asked:] == [(["in", "'b'", "config"], True)] * 3
    assert decided(sink)[-1][0] != ["in", "'b'", "config"]
    assert config.unforked
    hold_against_python(sink, {"config": {"b": 1}, "name": "zz"})


def test_a_walk_after_a_tracked_change_compares_nothing_and_marks_the_dict() -> None:
    config, sink = tracked({"b": 1, "cd": 2})
    name = ConcolicStr.made("b", "name", sink)
    config[name] = 0

    list(config)

    # as on v2, where the store is Python's own
    assert not any(part(expression, 0) == "==" for expression, _ in forks(sink))
    assert config.unforked


def test_a_later_walk_runs_a_stale_copy_s_lookup_as_on_v2() -> None:
    config, sink = tracked({"xx": 1, "yy": 2, "zz": 3})
    name = ConcolicStr.made("zz", "name", sink)
    keys = list(config)

    config.pop(name, None)
    for _key in config:
        pass
    asked = len(forks(sink))
    assert [key in config for key in keys] == [True, True, False]

    # the second walk follows the removal, so the dict runs as v2 runs it: a copy a walk
    # handed out is answered with no fork, and no tracked change is followed after it
    assert forks(sink)[asked:] == []
    assert config.unforked
    config[name] = 1
    assert "__setitem__" in downgrades(sink)


def test_a_store_over_a_key_a_change_moved_is_not_over_the_argument_s_place() -> None:
    config, sink = tracked({"bc": 2, "cd": 2})
    name = ConcolicStr.made("bc", "name", sink)

    config.pop(name, None)
    config[name] = 2
    made = config | {name: 0}
    asked = len(forks(sink))
    made.popitem()

    # the pop and the store put name's key last, so popitem compares no key of the argument
    # with it: an answer that makes name "cd" pops "bc" all the same
    assert not any(part(expression, 0) == "==" for expression, _ in forks(sink)[asked:])


def test_a_change_under_a_key_python_looked_up_is_python_s() -> None:
    config, sink = tracked({"cd": 2})
    name = ConcolicStr.made("zz", "name", sink)
    config["bc"] = 2

    # Python answers the lookup into the changed dict for name's value, with no fork
    assert config.get(name, 0) == 0
    config.pop(name, None)

    # so the removal under it records no fork naming name either, as on v2
    assert not any("name" in json.dumps(expression) for expression, _ in forks(sink))
    assert downgrades(sink) == ["get", "pop"]
    assert config.unforked

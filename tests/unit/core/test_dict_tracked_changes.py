"""A change under a tracked key: followed under a key of the dict's own kind, so each lookup
after it asks whether its key is the changed one, and Python's own under any other."""

from typing import Any

import pytest

from pyct.core.branch import Branch, Expression, Fact, SinkItem
from pyct.core.dict_changes import MOST_TRACKED_CHANGES
from pyct.core.dicts import ConcolicDict
from pyct.core.floats import ConcolicFloat
from pyct.core.ints import ConcolicInt
from pyct.core.list_state import plain
from pyct.core.strs import ConcolicStr
from tests.unit.core.python_forms import evaluate
from tests.unit.core.test_dicts import (
    decided,
    downgrades,
    forks,
    hold_against_python,
    plain_dict,
    tracked,
)


def part(expression: Expression, at: int) -> Expression:
    """One part of an expression that is a list, None for a leaf."""
    return expression[at] if isinstance(expression, list) else None


def test_a_plain_lookup_after_a_tracked_store_asks_whether_it_is_that_key() -> None:
    config, sink = tracked({"a": 1})
    name = ConcolicStr.made("k", "name", sink)

    config[name] = 5
    assert "b" not in config
    assert "k" in config

    assert forks(sink) == [
        (["in", "name", "config"], False),
        (["==", "name", "'b'"], False),
        (["in", "'b'", "config"], False),
        (["==", "name", "'k'"], True),
    ]
    assert downgrades(sink) == []
    hold_against_python(sink, {"config": {"a": 1}, "name": "k"})


def test_a_tracked_removal_answers_a_later_lookup_of_its_key() -> None:
    config, sink = tracked({"a": 1, "b": 2})
    name = ConcolicStr.made("a", "name", sink)

    del config[name]
    assert "a" not in config
    assert bool(config)

    assert forks(sink)[:2] == [(["in", "name", "config"], True), (["==", "name", "'a'"], True)]
    assert downgrades(sink) == []
    hold_against_python(sink, {"config": {"a": 1, "b": 2}, "name": "a"})


def test_a_later_change_under_a_plain_key_decides_alone() -> None:
    config, sink = tracked({})
    name = ConcolicStr.made("k", "name", sink)

    config[name] = 1
    config["b"] = 2
    before = len(forks(sink))
    assert "b" in config

    assert len(forks(sink)) == before
    assert forks(sink)[1:] == [(["==", "name", "'b'"], False), (["in", "'b'", "config"], False)]


def test_two_tracked_keys_ask_whether_they_are_equal() -> None:
    config, sink = tracked({})
    first = ConcolicStr.made("k", "n", sink)
    second = ConcolicStr.made("k", "m", sink)

    config[first] = 1
    config[second] = 2

    assert plain_dict(config) == {"k": 2}
    assert forks(sink) == [(["in", "n", "config"], False), (["==", "m", "n"], True)]
    hold_against_python(sink, {"config": {}, "n": "k", "m": "k"})


def test_keys_of_another_kind_are_never_the_changed_key() -> None:
    config, sink = tracked({})
    name = ConcolicStr.made("1", "name", sink)

    config[name] = 1
    assert 1 not in config

    assert forks(sink) == [(["in", "name", "config"], False), (["in", 1, "config"], False)]


def test_a_walk_s_key_from_before_a_tracked_change_is_looked_up_again() -> None:
    config, sink = tracked({"ab": 1})
    walked = next(iter(config))
    name = ConcolicStr.made("ab", "name", sink)

    config.pop(name)
    assert walked not in config

    assert forks(sink)[-1] == (["==", "name", "'ab'"], True)
    hold_against_python(sink, {"config": {"ab": 1}, "name": "ab"})


def test_a_walk_s_key_from_after_a_tracked_change_is_there() -> None:
    config, sink = tracked({"ab": 1})
    name = ConcolicStr.made("cd", "name", sink)

    config[name] = 2
    keys = list(config)
    before = len(forks(sink))

    assert all(key in config for key in keys)
    assert len(forks(sink)) == before


def int_keyed(sink: list[SinkItem]) -> Any:
    return ConcolicDict.made({}, "d", sink, int_keyed=True)


def test_a_tracked_int_into_an_int_keyed_dict_is_followed() -> None:
    sink: list[SinkItem] = []
    d = int_keyed(sink)

    d[ConcolicInt.made(0, "n", sink)] = 5
    assert bool(d)

    # the store's own fork settles the key, so the dict holds one on every input that takes it
    assert forks(sink) == [(["in", "n", "d"], False)]
    assert decided(sink) == [(["!=", ["+", ["len", "d"], 1], 0], True)]
    assert downgrades(sink) == []


@pytest.mark.parametrize(
    ("make", "keyed"),
    [
        (lambda sink: ConcolicStr.made("0", "n", sink), True),
        (lambda sink: ConcolicInt.made(0, "n", sink), False),
        (lambda sink: ConcolicFloat.made(1.5, "n", sink), False),
    ],
    ids=["str into dict[int, X]", "int elsewhere", "float"],
)
def test_a_tracked_key_of_another_kind_stays_python_s(make: Any, keyed: bool) -> None:
    sink: list[SinkItem] = []
    d = int_keyed(sink) if keyed else ConcolicDict.made({}, "d", sink)

    d[make(sink)] = 5

    assert downgrades(sink) == ["__setitem__"]
    assert not any(isinstance(item, Branch) for item in sink)
    # answered without a fork, so the dict is marked: nothing after it is decided
    assert d.unforked


def moves_a_fork(sink: list[SinkItem], args: dict[str, object]) -> bool:
    """Whether some recorded fork takes the other side on these arguments, so the path they
    would run is not the one recorded."""
    return any(evaluate(expression, args) != taken for expression, taken in forks(sink))


def test_a_walk_after_a_tracked_store_asks_which_key_it_named() -> None:
    config, sink = tracked({"ab": 1, "cd": 2})
    name = ConcolicStr.made("ab", "name", sink)

    config[name] = 0
    assert [plain(config[key]) for key in config] == [0, 2]

    assert (["==", "name", "'ab'"], True) in forks(sink)
    # that settles the name, so the key after it records no compare
    assert not any(expression == ["==", "name", "'cd'"] for expression, _ in forks(sink))
    hold_against_python(sink, {"config": {"ab": 1, "cd": 2}, "name": "ab"})
    # Python walks `[1, 0]` there: the path must keep that answer out
    assert moves_a_fork(sink, {"config": {"ab": 1, "cd": 2}, "name": "cd"})


def test_a_tracked_pop_from_a_changed_dict_reads_the_argument_under_the_key() -> None:
    config, sink = tracked({"a": 1, "b": 2})
    name = ConcolicStr.made("a", "name", sink)

    config["z"] = 0
    popped = config.pop(name)

    assert isinstance(popped, ConcolicInt) and popped.expression == ["[]", "config", "name"]
    assert downgrades(sink) == []
    hold_against_python(sink, {"config": {"a": 1, "b": 2}, "name": "a"})


@pytest.mark.parametrize(
    ("change", "name"),
    [
        (lambda config, n, m: config.update({n: 1, m: 2}), "update"),
        (lambda config, n, m: {n: 1, "x": 2} | config, "__ror__"),
        (lambda config, n, m: config | {n: 1, m: 2}, "__or__"),
    ],
    ids=["update", "ror", "or"],
)
def test_a_tracked_key_among_others_stays_python_s(change: Any, name: str) -> None:
    config, sink = tracked({})
    first = ConcolicStr.made("a", "n", sink)
    second = ConcolicStr.made("b", "m", sink)

    made = change(config, first, second)

    # Python compared the keys as it built them, recording a fork only where the hashes met
    assert name in downgrades(sink)
    assert not any(part(expression, 0) == "==" for expression, _ in forks(sink))
    # the dict the change made, or changed, is marked
    assert (made if isinstance(made, ConcolicDict) else config).unforked


def test_past_the_most_tracked_changes_a_change_is_python_s() -> None:
    config, sink = tracked({})
    keys = [ConcolicStr.made(f"k{j}", f"n{j}", sink) for j in range(MOST_TRACKED_CHANGES + 1)]

    for key in keys[:-1]:
        config[key] = 1
    assert downgrades(sink) == []
    assert not config.unforked
    config[keys[-1]] = 1

    assert downgrades(sink) == ["__setitem__"]
    assert config.unforked


def test_popitem_removes_the_key_a_tracked_store_put_last() -> None:
    config, sink = tracked({})
    name = ConcolicStr.made("b", "name", sink)

    config[name] = 5
    config.popitem()
    assert "b" not in config

    assert (["==", "name", "'b'"], True) in forks(sink)
    # there Python keeps "b": the store put "a" last, and popitem took it
    assert moves_a_fork(sink, {"config": {"b": 2}, "name": "a"})


def test_popitem_of_an_argument_s_key_asks_whether_a_tracked_store_was_over_it() -> None:
    config, sink = tracked({"a": 1, "b": 2})
    name = ConcolicStr.made("b", "name", sink)

    config[name] = 0
    config.popitem()

    compared = [fork for fork in forks(sink) if part(fork[0], 0) == "=="]
    assert compared == [(["==", "name", "'b'"], True)]
    # the key popitem read stays last on both sides of the compare: a place recorded before it
    at = next(
        at
        for at, item in enumerate(sink)
        if isinstance(item, Branch) and part(item.expression, 0) == "=="
    )
    before = sink[at - 1]
    assert isinstance(before, Fact)
    assert (before.expression, before.place) == (None, ["given", ["popped", "config", "'b'"]])


def test_a_walk_keeps_a_compared_key_in_place_on_its_compare_only() -> None:
    config, sink = tracked({"ab": 1, "cd": 2})
    name = ConcolicStr.made("ab", "name", sink)

    config[name] = 0
    list(config)

    places = [
        ("==", None) if not isinstance(item, Fact) else ("place", item.place)
        for item in sink
        if isinstance(item, Fact) or (isinstance(item, Branch) and part(item.expression, 0) == "==")
    ]
    # each pass keeps its key in place after it; the compare keeps it on both its sides, by a
    # given place recorded before it
    assert places == [
        ("place", ["walked", "config", "'ab'"]),
        ("place", ["given", ["walked", "config", "'ab'"]]),
        ("==", None),
        ("place", ["walked", "config", "'cd'"]),
    ]


@pytest.mark.parametrize(
    "change",
    [
        lambda config, n, alias, held: (config.__setitem__(n, 1), config.__setitem__(n, 2)),
        lambda config, n, alias, held: (config.__setitem__(n, 1), config.__setitem__(alias, 2)),
        lambda config, n, alias, held: config.pop(held, None),
    ],
    ids=["twice", "aliased", "removed"],
)
def test_a_walk_compares_no_key_the_path_keeps_apart(change: Any) -> None:
    config, sink = tracked({"ab": 1, "cd": 2})
    keys = [ConcolicStr.made(text, name, sink) for text, name in (("zz", "n"), ("zz", "m"))]
    # only a removal takes a key the argument holds, here "ab"
    change(config, *keys, ConcolicStr.made("ab", "h", sink))
    before = len(forks(sink))

    list(config)

    assert not any(part(expression, 0) == "==" for expression, _ in forks(sink)[before:])


def test_a_compare_the_path_already_decides_records_nothing() -> None:
    config, sink = tracked({"ab": 1, "cd": 2})
    name = ConcolicStr.made("zz", "name", sink)
    config[name] = 0

    assert "ab" in config and "ab" in config
    compares = [expression for expression, _ in forks(sink) if part(expression, 0) == "=="]

    assert compares == [["==", "name", "'ab'"]]


def test_a_walk_compares_no_store_that_put_its_key_last_again() -> None:
    config, sink = tracked({"ab": 1, "cd": 2})
    name = ConcolicStr.made("ab", "name", sink)
    config.pop(name)
    config[name] = 1
    before = len(forks(sink))

    list(config)

    # an answer that moves the name moves another key to the end: the walk reads it elsewhere
    assert not any(part(expression, 0) == "==" for expression, _ in forks(sink)[before:])


def test_a_shared_key_a_walk_handed_out_is_compared_as_any_other() -> None:
    config, sink = tracked({"c": 0})
    name = ConcolicStr.made("b", "name", sink)
    config[name] = 7
    # the walk hands out "b", a key Python shares with the literal below
    list(config)

    assert "b" in config

    assert (["==", "name", "'b'"], True) in forks(sink)
    hold_against_python(sink, {"config": {"c": 0}, "name": "b"})


def test_a_plain_lookup_reads_only_the_changes_after_its_key_s_own() -> None:
    config, sink = tracked({})
    name = ConcolicStr.made("k", "name", sink)
    config[name] = 1
    config["b"] = 2
    config["c"] = 3
    before = len(forks(sink))

    assert "b" in config

    assert forks(sink)[before:] == []


def test_a_shared_key_a_walk_handed_out_keeps_its_place_on_its_compare() -> None:
    # "b" is a key Python shares, so its lookup is not proven by the walk: it asks whether name
    # is "b", which holds only where the walk read "b", so the place is a fact before the fork
    config, sink = tracked({"b": 1})
    name = ConcolicStr.made("zz", "name", sink)

    config[name] = 2
    for key in list(config):
        assert config[key] >= 1

    at = next(
        at
        for at, item in enumerate(sink)
        if isinstance(item, Branch) and item.expression == ["==", "name", "'b'"]
    )
    before = sink[at - 1]
    assert isinstance(before, Fact)
    assert (before.expression, before.place) == (None, ["given", ["walked", "config", "'b'"]])


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


def test_a_stored_key_python_shares_is_compared_where_a_walk_hands_it_out() -> None:
    # n's own key "a" has no copy, so a lookup of what the walk handed out is a lookup of "a",
    # and asks whether n is "a": an answer that flips it walks another key there (see the
    # Cost of dict-keys-named-held-made-up-or-changed-under-a-tracked-key)
    config, sink = tracked({})
    name = ConcolicStr.made("a", "name", sink)

    config[name] = 0
    for key in config:
        assert key in config

    assert forks(sink) == [
        (["in", "name", "config"], False),
        (["==", "name", "'a'"], True),
        ([">", ["+", ["len", "config"], 1], 1], False),
    ]

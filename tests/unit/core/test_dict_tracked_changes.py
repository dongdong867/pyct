"""A change under a tracked key: followed under a key of the dict's own kind, so each lookup
after it asks whether its key is the changed one, and Python's own under any other."""

from typing import Any

import pytest

from pyct.core.branch import Branch, SinkItem
from pyct.core.dicts import ConcolicDict
from pyct.core.floats import ConcolicFloat
from pyct.core.ints import ConcolicInt
from pyct.core.list_state import plain
from pyct.core.strs import ConcolicStr
from tests.unit.core.python_forms import evaluate
from tests.unit.core.test_dicts import downgrades, forks, hold_against_python, plain_dict, tracked


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

    assert forks(sink) == [(["in", "n", "d"], False), (["!=", ["+", ["len", "d"], 1], 0], True)]
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
    assert (["==", "name", "'cd'"], False) in forks(sink)
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


def test_a_merge_on_the_left_keeps_its_own_keys_apart() -> None:
    config, sink = tracked({})
    name = ConcolicStr.made("a", "name", sink)

    merged = {name: 1, "x": 2} | config

    assert (["==", "name", "'x'"], False) in forks(sink)
    assert moves_a_fork(sink, {"config": {}, "name": "x"})
    assert plain_dict(merged) == {"a": 1, "x": 2}

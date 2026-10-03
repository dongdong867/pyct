"""A tracked dict: its lookups, its size, its walks and views, its changes, and its compares.

Every fork a dict records is a condition on the argument it came from, so the tests hold each
against Python by evaluating it over the argument as the target was called with it.
"""

import copy
from collections.abc import Callable
from typing import Any

import pytest

from pyct.core import bound
from pyct.core.bools import ConcolicBool
from pyct.core.branch import Branch, Downgrade, Expression, Fact, SinkItem
from pyct.core.dicts import ConcolicDict
from pyct.core.ints import ConcolicInt
from pyct.core.list_state import plain
from pyct.core.strs import ConcolicStr
from pyct.core.values import raised_by_target
from tests.unit.core.python_forms import evaluate


def tracked(values: dict[str, Any], name: str = "config") -> tuple[Any, list[SinkItem]]:
    """A tracked dict of the values, each int and str tracked under its key, and its sink."""
    sink: list[SinkItem] = []
    items: dict[object, object] = {}
    for key, value in values.items():
        access: Expression = ["[]", name, repr(key)]
        if isinstance(value, str):
            items[key] = ConcolicStr.made(value, access, sink)
        elif isinstance(value, int) and not isinstance(value, bool):
            items[key] = ConcolicInt.made(value, access, sink)
        else:
            items[key] = value
    return ConcolicDict.made(items, name, sink), sink


def forks(sink: list[SinkItem]) -> list[tuple[Expression, bool]]:
    return [(item.expression, item.taken) for item in sink if isinstance(item, Branch)]


def decided(sink: list[SinkItem]) -> list[tuple[Expression, bool]]:
    """Each check the sink holds as a fact, with the side it took."""
    return [
        (item.expression, item.taken)
        for item in sink
        if isinstance(item, Fact) and item.expression is not None
    ]


def downgrades(sink: list[SinkItem]) -> list[str]:
    return [item.name for item in sink if isinstance(item, Downgrade)]


def plain_dict(config: object) -> dict[object, object]:
    """What a dict holds, each value plain, read without recording anything."""
    assert isinstance(config, dict)
    return {key: plain(value) for key, value in dict.items(config)}


def hold_against_python(sink: list[SinkItem], args: dict[str, object]) -> None:
    """Each fork the dict recorded is what Python answers over the arguments as called."""
    for expression, taken in forks(sink):
        assert evaluate(expression, args) == taken, expression


# each program a target may run on a dict it was given, as a target writes it; `name` is a
# tracked str the tests put in beside it
PROGRAMS: dict[str, Callable[[Any, Any], object]] = {
    "in": lambda c, name: ("a" in c, "z" in c, "a" not in c),
    "get": lambda c, name: (c.get("a"), c.get("z"), c.get("z", 9)),
    "index": lambda c, name: c["a"] + c["a"],
    "missing": lambda c, name: c["z"],
    "truth": lambda c, name: bool(c),
    "store": lambda c, name: (c.__setitem__("n", 7), c.__setitem__("a", 3), bool(c), list(c)),
    "del": lambda c, name: (c.__delitem__("a"), bool(c), list(c.values())),
    "del missing": lambda c, name: c.__delitem__("z"),
    "pop": lambda c, name: (c.pop("a"), c.pop("z", 0), list(c)),
    "pop missing": lambda c, name: c.pop("z"),
    "popitem": lambda c, name: (c.popitem(), c.popitem(), c.popitem()),
    "setdefault": lambda c, name: (c.setdefault("a", 1), c.setdefault("n"), list(c.items())),
    "update": lambda c, name: (c.update({"a": 0, "n": 1}, m=2), list(c.keys())),
    "update pairs": lambda c, name: (c.update([("x", 1)]), bool(c)),
    "clear": lambda c, name: (c.clear(), bool(c), "a" in c),
    "keys": lambda c, name: (list(c.keys()), c.keys().__contains__("a"), list(reversed(c.keys()))),
    "values": lambda c, name: (list(c.values()), 1 in c.values(), list(reversed(c.values()))),
    "items": lambda c, name: (list(c.items()), ("a", 1) in c.items(), ("a", 5) in c.items()),
    "not a pair": lambda c, name: ("a" in c.items(), ("a", 1, 2) in c.items()),
    "walk": lambda c, name: [c[key] for key in c],
    "reversed": lambda c, name: list(reversed(c)),
    "copy": lambda c, name: (c.copy().pop("a"), "a" in c, copy.copy(c)["b"]),
    "or": lambda c, name: sorted(c | {"n": 1, "a": 2}),
    "ror": lambda c, name: list({"n": 1, "a": 2} | c),
    "ior": lambda c, name: (c.__ior__({"n": 1}), bool(c)),
    "equal": lambda c, name: (c == {"a": 1, "b": "x"}, c != {"a": 1}, c == {"a": 1, "c": 2}),
    "equal values": lambda c, name: c == {"a": 2, "b": "x"},
    "equal itself": lambda c, name: c == c.copy(),
    "tracked in": lambda c, name: (name in c, c.get(name), c.get(name, 0)),
    "tracked index": lambda c, name: c[name],
    "tracked pop": lambda c, name: c.pop(name, None),
}


@pytest.mark.parametrize("name", PROGRAMS)
@pytest.mark.parametrize("key", ["a", "k"])
def test_a_program_answers_as_python_and_each_fork_holds_over_the_argument(
    name: str, key: str
) -> None:
    config, sink = tracked({"a": 1, "b": "x"})
    argument = {"a": 1, "b": "x"}
    tracked_key = ConcolicStr.made(key, "name", sink)
    expected: dict[object, object] = {}
    expected.update(argument)
    try:
        wanted: object = PROGRAMS[name](expected, key)
    except (KeyError, TypeError) as error:
        with pytest.raises(type(error)) as raised:
            PROGRAMS[name](config, tracked_key)
        assert raised_by_target(raised.value)
    else:
        assert _plain(PROGRAMS[name](config, tracked_key)) == wanted
    assert plain_dict(config) == expected
    hold_against_python(sink, {"config": argument, "name": key})


def _plain(value: object) -> object:
    if isinstance(value, tuple | list):
        return type(value)(_plain(part) for part in value)
    if isinstance(value, dict):
        return plain_dict(value)
    return plain(value)


def test_a_lookup_records_its_fork_the_first_time_and_a_fact_each_time_after() -> None:
    config, sink = tracked({"total": 5})

    assert "coupon" not in config
    assert config.get("tip", 0) == 0
    assert config["total"] > 100 or config["total"] < 0 or True
    assert "coupon" not in config

    assert forks(sink) == [
        (["in", "'coupon'", "config"], False),
        (["in", "'tip'", "config"], False),
        (["in", "'total'", "config"], True),
        ([">", ["[]", "config", "'total'"], 100], False),
        (["<", ["[]", "config", "'total'"], 0], False),
    ]
    # the path settled each key the first time: a later lookup holds what that one found
    assert decided(sink) == [
        (["in", "'total'", "config"], True),
        (["in", "'coupon'", "config"], False),
    ]


def test_a_missing_key_raises_after_its_fork() -> None:
    config, sink = tracked({})

    with pytest.raises(KeyError, match="'port'"):
        config["port"]

    assert forks(sink) == [(["in", "'port'", "config"], False)]


def test_the_size_is_the_argument_s_plus_what_the_target_changed() -> None:
    config, sink = tracked({"a": 0, "b": 1})

    config["seen"] = 1
    del config["a"]
    config["b"] = 5
    config["new"] = 2

    # a and b were found in the argument, and one key more was added than removed
    assert bool(config)
    assert decided(sink)[-1] == (["!=", ["+", ["len", "config"], 1], 0], True)
    config.pop("seen")
    config.pop("new")
    assert bool(config)
    assert decided(sink)[-1] == (["!=", ["-", ["len", "config"], 1], 0], True)
    assert "seen" not in config and "a" not in config
    assert forks(sink).count((["in", "'seen'", "config"], False)) == 1


def test_len_where_pyct_binds_it_is_the_size_term() -> None:
    config, sink = tracked({"a": 0})
    config["b"] = 1

    size = bound.len(config)
    views = [bound.len(config.keys()), bound.len(config.values()), bound.len(config.items())]

    assert size == 2 and type(size) is ConcolicInt
    assert size.expression == ["+", ["len", "config"], 1]
    assert views == [2, 2, 2]
    assert all(type(view) is ConcolicInt for view in views)
    assert downgrades(sink) == []


@pytest.mark.parametrize(("start", "filled"), [({}, False), ({"a": 0}, True)])
@pytest.mark.parametrize(
    "read",
    [lambda c: c, lambda c: c.keys(), lambda c: c.values(), lambda c: c.items()],
    ids=["dict", "keys", "values", "items"],
)
def test_pyct_s_bool_is_the_truth_test_untested(
    start: dict[str, int], filled: bool, read: Callable[[Any], object]
) -> None:
    config, sink = tracked(start)

    truth = bound.bool_(read(config))

    # the condition `if config:` tests, recorded only where the target tests it
    assert isinstance(truth, ConcolicBool) and int.__bool__(truth) is filled
    assert truth.expression == ["!=", ["len", "config"], 0]
    assert forks(sink) == [] and downgrades(sink) == []
    assert bool(truth) is filled
    assert forks(sink) == [(["!=", ["len", "config"], 0], filled)]


def test_pyct_s_bool_keeps_the_size_the_dict_had_at_the_call() -> None:
    config, sink = tracked({"a": 0})
    del config["a"]

    truth = bound.bool_(config)
    config["b"] = 1

    assert truth.expression == ["!=", ["-", ["len", "config"], 1], 0]
    assert int.__bool__(truth) is False
    assert forks(sink) == [(["in", "'a'", "config"], True), (["in", "'b'", "config"], False)]


@pytest.mark.parametrize(
    "read",
    [lambda c: c, lambda c: c.keys(), lambda c: c.values(), lambda c: c.items()],
    ids=["dict", "keys", "values", "items"],
)
def test_pyct_s_bool_of_a_dict_that_holds_a_key_on_every_input_is_a_fact(
    read: Callable[[Any], object],
) -> None:
    config, sink = tracked({})
    config["a"] = 0

    truth = bound.bool_(read(config))

    # recorded where `bool` is called, so the test of what it answers records nothing
    assert truth is True
    assert decided(sink) == [(["!=", ["+", ["len", "config"], 1], 0], True)]
    assert forks(sink) == [(["in", "'a'", "config"], False)]


def test_a_truth_test_of_a_dict_that_holds_a_key_on_every_input_is_a_fact() -> None:
    config, sink = tracked({"a": 1})

    assert "a" in config
    assert config and config.keys()
    del config["a"]
    assert not config

    filled = ["!=", ["len", "config"], 0]
    # the removal looks a up again, which the path settled
    assert decided(sink) == [(filled, True), (filled, True), (["in", "'a'", "config"], True)]
    # with a removed, nothing says the dict holds a key, so its truth is a fork
    assert forks(sink)[-1] == (["!=", ["-", ["len", "config"], 1], 0], False)


def test_pyct_s_bool_of_a_dict_whose_form_stopped_describing_it_is_plain() -> None:
    config, sink = tracked({})
    dict.__setitem__(config, "z", 0)

    truth = bound.bool_(config)

    assert truth is True
    assert downgrades(sink) == ["__bool__"] and forks(sink) == []
    assert bound.bool_(config.keys()) is True and downgrades(sink) == ["__bool__"]


def test_pyct_s_bool_through_map_is_each_dict_s_truth() -> None:
    sink: list[SinkItem] = []
    rows = [ConcolicDict.made({}, ["[]", "cfgs", at], sink) for at in range(2)]

    truths = list(bound.map_(bool, rows))

    assert [truth.expression for truth in truths] == [
        ["!=", ["len", ["[]", "cfgs", at]], 0] for at in range(2)
    ]
    assert forks(sink) == []


def test_python_s_len_is_a_downgrade_but_for_a_walk_s_own_guess() -> None:
    config, sink = tracked({"a": 0, "b": 1})

    assert list(config) == ["a", "b"]
    assert list(config.values()) == [0, 1]
    assert downgrades(sink) == []
    assert len(config) == 2 and len(config.keys()) == 2
    assert downgrades(sink) == ["__len__", "__len__"]


def test_a_walk_forks_on_each_key_and_settles_none_of_them() -> None:
    config, sink = tracked({"a": 0, "b": "x"})

    pairs = list(config.items())

    assert [key for key, _ in pairs] == ["a", "b"] and type(pairs[0][0]) is str
    assert [value.expression for _, value in pairs] == [
        ["[]", "config", "'a'"],
        ["[]", "config", "'b'"],
    ]
    # a walk is not a lookup: the first lookup after it records whether its key is there
    assert config["a"] == 0 and "b" in config
    assert forks(sink) == [
        ([">", ["len", "config"], 0], True),
        ([">", ["len", "config"], 1], True),
        ([">", ["len", "config"], 2], False),
        (["in", "'a'", "config"], True),
        (["==", ["[]", "config", "'a'"], 0], True),
        (["in", "'b'", "config"], True),
    ]


def test_a_walk_keeps_the_key_it_read_at_its_place_as_a_fact_after_its_pass() -> None:
    config, sink = tracked({"a": 0, "b": 1})
    config["n"] = 2

    assert list(config) == ["a", "b", "n"]
    assert list(reversed(config)) == ["n", "b", "a"]
    assert config.popitem() == ("n", 2)
    assert config.popitem() == ("b", 1)

    # B a fork, F a fact: the store's lookup of n; then, as n is a key on every input, the
    # first pass is a fact with its place, each later pass a fork and its place, and the end a
    # fork; the same from the end, whose first key, n, is the target's own and pins nothing;
    # popitem's forks, the second with its place; and the test's own compare of the value
    shape = "B FBFBFB FBFBFB BBF B".replace(" ", "")
    assert "".join("F" if isinstance(item, Fact) else "B" for item in sink) == shape
    assert [item.place for item in sink if isinstance(item, Fact)] == [
        ["walked", "config", "'a'"],
        ["walked", "config", "'b'"],
        ["exactly", "config"],  # the target's own key: the argument holds only its own keys
        None,
        ["last", "config", "'b'"],
        ["last", "config", "'a'"],
        ["popped", "config", "'b'"],
    ]
    grown = ["+", ["len", "config"], 1]
    assert [item.expression for item in sink if isinstance(item, Fact)][:2] == [
        [">", grown, 0],
        None,
    ]


def test_a_walk_from_the_end_forks_as_one_from_the_start() -> None:
    config, sink = tracked({"a": 0, "b": 1})

    assert list(reversed(config)) == ["b", "a"]
    assert list(reversed(config.items())) == [("b", 1), ("a", 0)]
    assert forks(sink)[:3] == [
        ([">", ["len", "config"], 0], True),
        ([">", ["len", "config"], 1], True),
        ([">", ["len", "config"], 2], False),
    ]


def test_a_change_while_it_walks_raises_python_s_own_error() -> None:
    config, _ = tracked({"a": 0})

    with pytest.raises(RuntimeError) as raised:
        for key in config:
            config[key + "!"] = 1

    assert raised_by_target(raised.value)


def test_a_tracked_key_is_looked_up_by_its_expression() -> None:
    config, sink = tracked({"apple": 1})
    name = ConcolicStr.made("apple", "name", sink)

    assert name in config
    read = config[name]

    assert type(read) is ConcolicInt and read.expression == ["[]", "config", "name"]
    assert forks(sink) == [(["in", "name", "config"], True)]
    assert decided(sink) == [(["in", "name", "config"], True)]


def test_a_tracked_key_into_a_changed_dict_is_python_s_answer() -> None:
    config, sink = tracked({"apple": 1})
    name = ConcolicStr.made("apple", "name", sink)
    config["pear"] = 2

    assert name in config
    assert config[name] == 1 and type(config[name]) is ConcolicInt

    assert downgrades(sink) == ["__contains__", "__getitem__", "__getitem__"]


# see-why: a fork taken before KeyError is marked as the lookup's that may raise; a lookup with
# a default, a test with `in` and a walk raise nothing
RAISING: dict[str, tuple[Callable[[Any], object], bool]] = {
    "index": (lambda d: d["a"], True),
    "del": (lambda d: d.__delitem__("a"), True),
    "pop": (lambda d: d.pop("a"), True),
    "popitem": (lambda d: d.popitem(), True),
    "get": (lambda d: d.get("a"), False),
    "pop with a default": (lambda d: d.pop("a", 0), False),
    "in": (lambda d: "a" in d, False),
    "walk": (lambda d: list(d), False),
}


@pytest.mark.parametrize("program", RAISING, ids=list(RAISING))
def test_marks_a_fork_before_key_error_as_raising(program: str) -> None:
    config, sink = tracked({"a": 1})
    run, raising = RAISING[program]

    run(config)

    marked = [item.raising for item in sink if isinstance(item, Branch)]
    assert marked and marked[0] is raising and not any(marked[1:])


def test_a_tracked_key_found_counts_as_one_key_only_where_no_plain_key_was_found() -> None:
    config, sink = tracked({"a": 1, "b": 2})
    name = ConcolicStr.made("a", "name", sink)

    assert config.fewest() == 0
    assert name in config
    # the tracked key may equal any key, so it counts one, and a plain one found adds nothing
    assert config.fewest() == 1
    assert "a" in config
    assert config.fewest() == 1
    assert "b" in config and "z" not in config
    assert config.fewest() == 2
    config["z"] = 0
    assert config.fewest() == 3

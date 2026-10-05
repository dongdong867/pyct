"""The key a small dict's own walk hands out: a tracked key named by its pass, which the solver
may choose (let-the-solver-choose-a-small-dict-s-walk-key)."""

import builtins
from typing import Any

import pytest

from pyct.core.bound import BOUND
from pyct.core.branch import Fact, SinkItem
from pyct.core.dicts import ConcolicDict
from pyct.core.floats import ConcolicFloat
from pyct.core.ints import ConcolicInt
from pyct.core.strs import ConcolicStr
from tests.unit.core.test_dicts import decided, downgrades, forks, tracked

# builtins as pyct binds them in a module of the target's package
_TARGETS: dict[str, Any] = {**vars(builtins), "len": BOUND["len"][1]}


def in_the_target(source: str, **names: object) -> dict[str, Any]:
    """Run ``source`` as code of the target's package runs, with ``names`` bound, and hand back
    what it bound."""
    scope: dict[str, Any] = {"__builtins__": _TARGETS, **names}
    exec(compile(source, "target.py", "exec"), scope)  # noqa: S102
    return scope


def places(sink: list[SinkItem]) -> list[object]:
    return [item.place for item in sink if isinstance(item, Fact) and item.place is not None]


def test_the_target_s_own_for_hands_out_a_key_named_by_its_pass() -> None:
    config, sink = tracked({"alpha": 1, "beta": 2})

    scope = in_the_target("keys = [k for k in config]", config=config)

    keys = scope["keys"]
    assert keys == ["alpha", "beta"]
    assert [type(key) for key in keys] == [ConcolicStr, ConcolicStr]
    assert [key.expression for key in keys] == [["key", "config", 0], ["key", "config", 1]]
    assert places(sink) == [
        ["walked", "config", ["key", "config", 0]],
        ["walked", "config", ["key", "config", 1]],
    ]


@pytest.mark.parametrize(
    "source",
    [
        "for k in config.keys(): read.append(config[k])",
        "for v in config.values(): read.append(v)",
        "for k, v in config.items(): read.append(v)",
    ],
    ids=["keys", "values", "items"],
)
def test_a_view_s_walk_reads_each_value_under_its_walk_key(source: str) -> None:
    config, sink = tracked({"alpha": 1, "beta": 2})

    read: list[Any] = []
    in_the_target(source, config=config, read=read)

    assert read == [1, 2]
    assert [value.expression for value in read] == [
        ["[]", "config", ["key", "config", 0]],
        ["[]", "config", ["key", "config", 1]],
    ]
    # the walk read each key, so a lookup of it is a fact of the path, never a fork
    assert [part for part, _ in forks(sink) if isinstance(part, list) and part[0] == "in"] == []


def test_a_lookup_of_a_walk_key_is_a_fact_and_another_key_s_a_fork() -> None:
    numbers = ConcolicDict.made({1: 9}, "d", sink := [], int_keyed=True)

    in_the_target(
        "for k in d:\n    k in d\n    d.get(k)\n    1 in d\n    1 in d",
        d=numbers,
    )

    assert decided(sink) == [(["in", ["key", "d", 0], "d"], True)] * 2 + [(["in", 1, "d"], True)]
    assert (["in", 1, "d"], True) in forks(sink)


def test_a_compare_on_a_walk_key_is_a_fork() -> None:
    config, sink = tracked({"x": 9})

    in_the_target("for k in config:\n    if k == 'admin':\n        pass", config=config)

    assert (["==", ["key", "config", 0], "'admin'"], False) in forks(sink)


@pytest.mark.parametrize(
    "source",
    [
        "list(config)",
        "sorted(config)",
        "tuple(config)",
        "set(config)",
        "list(reversed(config))",
        "next(iter(config))",
        "dict(config)",
        "{**config}",
        "a, = config",
        "list(enumerate(config))",
    ],
)
def test_a_walk_python_makes_hands_out_today_s_keys(source: str) -> None:
    config, sink = tracked({"alpha": 1})

    in_the_target(source, config=config)

    assert "key" not in repr(places(sink))


def test_a_walk_outside_the_target_s_package_hands_out_today_s_keys() -> None:
    config, sink = tracked({"alpha": 1})

    keys = [key for key in config]

    assert [type(key) for key in keys] == [str]
    assert places(sink) == [["walked", "config", "'alpha'"]]


@pytest.mark.parametrize(
    "values",
    [
        {"a": 1.5},
        {"a": True},
        {"a": [1]},
        {"a": None},
    ],
    ids=["a-float", "a-bool", "a-list", "none"],
)
def test_a_dict_the_solver_cannot_choose_in_hands_out_today_s_keys(values: dict[str, Any]) -> None:
    sink: list[SinkItem] = []
    items: dict[object, object] = {
        key: ConcolicFloat.made(value, ["[]", "d", repr(key)], sink)
        if type(value) is float
        else value
        for key, value in values.items()
    }
    walked = ConcolicDict.made(items, "d", sink)

    keys = in_the_target("keys = [k for k in d]", d=walked)["keys"]

    assert all(type(key) is str for key in keys)


def test_a_dict_of_mixed_keys_hands_out_today_s_keys() -> None:
    walked = ConcolicDict.made({"a": 1, 2: 3}, "d", [])

    keys = in_the_target("keys = [k for k in d]", d=walked)["keys"]

    assert [type(key) for key in keys] == [str, int]


def test_a_changed_dict_hands_out_today_s_keys() -> None:
    config, _ = tracked({"a": 9})
    config["zz"] = 0

    keys = in_the_target("keys = [k for k in config]", config=config)["keys"]

    assert [type(key) for key in keys] == [str, str]


def test_a_store_under_a_walk_key_keeps_it_at_the_input_s_key() -> None:
    config, sink = tracked({"alpha": 1, "beta": 2})

    in_the_target("for k in config:\n    config[k] = 0", config=config)

    assert (["==", ["key", "config", 0], "'alpha'"], True) in decided(sink)
    # the store is the plain key's, and the rest of the walk hands out today's keys
    assert config.log[0][0] is None
    assert ["walked", "config", "'beta'"] in places(sink)
    assert downgrades(sink) == []


def test_a_walk_key_is_an_int_under_int_keys() -> None:
    numbers = ConcolicDict.made({7: ConcolicInt.made(1, ["[]", "d", 7], [])}, "d", [])

    keys = in_the_target("keys = [k for k in d]", d=numbers)["keys"]

    assert type(keys[0]) is ConcolicInt and keys[0] == 7


def test_a_dict_built_with_the_argument_s_keys_after_others_hands_out_today_s_keys() -> None:
    # `{"b": 0} | config` holds the argument's keys in another order: its walk reads no key at
    # the argument's pass
    config, _ = tracked({"a": 1, "b": 2})

    keys = in_the_target("keys = [k for k in {'b': 0} | config]", config=config)["keys"]

    assert keys == ["b", "a"] and [type(key) for key in keys] == [str, str]


def test_a_dict_past_the_cap_hands_out_walk_keys_too() -> None:
    # an answer that grows a dict past the cap walks it as the path did; the solver chooses
    # keys only in a small dict
    config, _ = tracked({f"k{at}": at for at in range(250)})

    keys = in_the_target("keys = [k for k in config]", config=config)["keys"]

    assert keys[249].expression == ["key", "config", 249]


@pytest.mark.parametrize(
    "source",
    [
        "out = {k: v + 1 for k, v in config.items()}\nif 'a' in out:\n    pass",
        "s = set()\nfor k in config:\n    s.add(k)\nif 'a' in s:\n    pass",
        "e = {}\nfor k in config:\n    e[k] = config[k]\nif e.get('a'):\n    pass",
        "for k in config:\n    if k in ('a', 'b') and k in ['a']:\n        pass",
    ],
    ids=["comprehension", "set", "store", "containers"],
)
def test_python_s_own_lookup_compares_a_walk_key_plainly(source: str) -> None:
    # a plain dict or set compares a stored walk key only where two hashes meet: a fork there
    # would hold on some inputs only, so the compare is the plain key's, as before walk keys
    config, sink = tracked({"a": 1, "bb": 2})

    in_the_target(source, config=config)

    assert [part for part, _ in forks(sink) if isinstance(part, list) and part[0] == "=="] == []


def test_a_compare_the_target_writes_on_a_walk_key_is_a_fork_beside_a_container() -> None:
    config, sink = tracked({"a": 1})

    in_the_target("for k in config:\n    if k != 'zz':\n        pass", config=config)

    assert (["!=", ["key", "config", 0], "'zz'"], True) in forks(sink)


@pytest.mark.parametrize(
    "source",
    [
        "s = {k for k in config}",
        "keys = [k for k in config]\nmax(keys)",
        "names = ['zz']\nfor k in config:\n    k in names",
    ],
    ids=["hashed", "sorted-by-max", "a-list-search"],
)
def test_a_walk_key_python_s_own_code_takes_escapes(source: str) -> None:
    # a fact keeps it at the input's key, so no ask chooses it, and from then on it compares as
    # its plain key, recording no fork
    config, sink = tracked({"a": 1, "bb": 2})

    in_the_target(f"{source}\nfor k in config:\n    pass", config=config)
    keys = in_the_target("keys = [k for k in config]\nkeys[0].__hash__()", config=config)["keys"]
    in_the_target("if keys[0] == 'zz':\n    pass", keys=keys)

    assert (["==", ["key", "config", 0], "'a'"], True) in decided(sink)
    assert [part for part, _ in forks(sink) if isinstance(part, list) and part[0] == "=="] == []


def test_a_walk_key_an_untaught_operation_takes_escapes() -> None:
    config, sink = tracked({"ab": 1})

    in_the_target("for k in config:\n    k.encode()", config=config)

    assert (["==", ["key", "config", 0], "'ab'"], True) in decided(sink)

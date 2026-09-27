"""A tracked dict changed, copied, merged, compared, pickled and emptied, and the forms of its
operations pyct does not follow, each Python's own answer."""

import copy
import pickle
import re
import time
from collections.abc import Callable, KeysView
from typing import Any

import pytest

from pyct.core import bound
from pyct.core.branch import Expression
from pyct.core.dict_views import ConcolicItems, ConcolicKeys, ConcolicValues
from pyct.core.dicts import ConcolicDict
from pyct.core.ints import ConcolicInt
from pyct.core.list_state import kind_of
from pyct.core.lists import ConcolicList
from pyct.core.strs import ConcolicStr
from pyct.core.values import raised_by_target
from tests.unit.core.test_dicts import downgrades, forks, plain_dict, tracked


def test_a_change_under_a_tracked_key_is_python_s_own_and_the_dict_goes_on() -> None:
    config, sink = tracked({"a": 1})
    name = ConcolicStr.made("b", "name", sink)

    config[name] = 1
    config.setdefault(name, 5)
    config.pop(name)
    config[name] = 2
    del config[name]

    assert plain_dict(config) == {"a": 1}
    assert bool(config)
    assert forks(sink)[-1] == (["!=", ["len", "config"], 0], True)
    # each call is named once, its lookup and its change together
    assert downgrades(sink) == ["__setitem__", "setdefault", "pop", "__setitem__", "__delitem__"]


def test_a_key_of_another_kind_is_python_s_answer() -> None:
    config, sink = tracked({"a": 1})

    assert (1, 2) not in config
    config[(1, 2)] = 3
    assert config.get((1, 2)) == 3
    assert config.setdefault((3, 4), 5) == 5
    assert config.pop((1, 2)) == 3
    assert config.pop((5, 6), 0) == 0
    assert bool(config)

    assert forks(sink) == [(["!=", ["+", ["len", "config"], 1], 0], True)]
    assert downgrades(sink) == [
        "__contains__",
        "__setitem__",
        "get",
        "setdefault",
        "pop",
        "pop",
    ]


@pytest.mark.parametrize(
    "program",
    [
        lambda c: c[[1]],
        lambda c: [1] in c,
        lambda c: c.__setitem__([1], 0),
        lambda c: c.pop([1]),
        lambda c: c.__delitem__([1]),
        lambda c: c.setdefault([1]),
    ],
)
def test_a_key_python_cannot_hash_raises_python_s_own_error(
    program: Callable[[Any], object],
) -> None:
    config, _ = tracked({"a": 1})
    with pytest.raises(TypeError) as python:
        program({"a": 1})

    with pytest.raises(TypeError, match=re.escape(str(python.value))) as raised:
        program(config)

    assert raised_by_target(raised.value)


def test_storing_a_value_no_expression_holds_turns_the_dict_plain() -> None:
    config, sink = tracked({"a": 1})

    config["o"] = object()
    assert bool(config)

    assert downgrades(sink) == ["__setitem__"]
    assert forks(sink) == []
    assert type(dict.__getitem__(config, "a")) is int


def test_values_an_expression_holds_are_stored() -> None:
    config, sink = tracked({"a": 1})

    looped: list[object] = [1]
    looped.append(looped)
    config["looped"] = looped
    config["list"] = [1, "s", None, 1.5, True, {"k": [2]}]
    config["itself"] = config.get("list")

    assert downgrades(sink) == []


def test_a_change_made_without_the_methods_turns_the_dict_plain_at_the_next_read() -> None:
    config, sink = tracked({"a": 1})

    dict.__setitem__(config, "z", 0)
    assert "a" in config
    assert bool(config)

    assert forks(sink) == []
    assert downgrades(sink) == ["__contains__"]
    assert config.copy() == {"a": 1, "z": 0}


def test_a_walk_goes_on_plain_where_the_dict_changed_without_its_methods() -> None:
    config, sink = tracked({"a": 1, "b": 2})
    walked = iter(config.values())

    first = next(walked)
    dict.__setitem__(config, "b", 5)

    assert [first, *walked] == [1, 5]
    assert downgrades(sink) == ["__iter__"]


def test_two_dicts_compare_sizes_first_then_each_key_and_its_value() -> None:
    config, sink = tracked({})
    other, other_sink = tracked({"mode": "slow"})

    assert config != {"mode": "fast"}
    assert (other == {"mode": "fast"}) is False
    assert (other == 5) is False

    assert forks(sink) == [(["==", ["len", "config"], 1], False)]
    assert forks(other_sink) == [
        (["==", ["len", "config"], 1], True),
        (["in", "'mode'", "config"], True),
        (["==", ["[]", "config", "'mode'"], "'fast'"], False),
    ]


def test_two_tracked_dicts_compare_by_the_left_one_s_keys() -> None:
    left, sink = tracked({"a": 1}, "left")
    right = ConcolicDict.made(
        {"a": ConcolicInt.made(1, ["[]", "right", "'a'"], sink)}, "right", sink
    )

    assert left == right

    assert forks(sink) == [
        (["==", ["len", "left"], ["len", "right"]], True),
        (["in", "'a'", "right"], True),
        (["==", ["[]", "right", "'a'"], ["[]", "left", "'a'"]], True),
    ]


def test_copies_share_what_the_path_settled() -> None:
    config, sink = tracked({"a": 1})

    copied = config.copy()
    assert "a" in copied and "a" in config and "a" in copy.copy(config)
    deep = copy.deepcopy(config)
    assert "a" in deep and type(deep) is ConcolicDict

    assert forks(sink) == [(["in", "'a'", "config"], True)]


def test_a_merge_either_way_is_a_tracked_dict_of_the_argument() -> None:
    config, sink = tracked({"a": 1})

    right = config | {"n": 2}
    left = {"n": 2, "a": 5} | config

    assert list(left) == ["n", "a"] and left["a"] == 1
    assert bool(right) and bool(left)
    assert forks(sink)[-2:] == [
        (["!=", ["+", ["len", "config"], 1], 0], True),
        (["!=", ["+", ["len", "config"], 1], 0], True),
    ]
    assert config.__or__(5) is NotImplemented and config.__ror__(5) is NotImplemented


def test_clear_leaves_a_plain_dict() -> None:
    config, sink = tracked({"a": 1})

    config.clear()
    config["b"] = 2

    assert bool(config) and forks(sink) == [] and downgrades(sink) == []


def test_a_pickle_holds_the_plain_dict() -> None:
    config, sink = tracked({"a": 1})

    loaded = pickle.loads(pickle.dumps(config))

    assert loaded == {"a": 1} and type(loaded) is dict and type(loaded["a"]) is int
    assert downgrades(sink) == ["__reduce_ex__"]


def test_a_view_answers_a_set_operation_as_python_and_names_it() -> None:
    config, sink = tracked({"a": 1, "b": 2})

    assert config.keys() & {"a"} == {"a"}
    assert {"a"} & config.keys() == {"a"}
    assert config.items() | {("c", 3)} == {("a", 1), ("b", 2), ("c", 3)}
    assert config.keys().isdisjoint({"z"})
    assert config.keys() == {"a", "b"}

    assert downgrades(sink) == ["__and__", "__rand__", "__or__", "isdisjoint", "__eq__"]
    assert forks(sink) == []
    assert isinstance(config.keys(), KeysView)
    assert repr(config.keys()) == "dict_keys(['a', 'b'])"
    assert dict(config.keys().mapping) == {"a": 1, "b": 2}


def test_a_view_s_truth_test_is_the_dict_s() -> None:
    config, sink = tracked({})

    assert not config.values()

    assert forks(sink) == [(["!=", ["len", "config"], 0], False)]
    with pytest.raises(TypeError) as python:
        hash({}.keys())
    # Python names the view's own type, which a tracked dict's view is not
    words = re.escape(str(python.value)).replace("dict_keys", ".+")
    with pytest.raises(TypeError, match=words):
        hash(config.keys())


def test_a_taught_method_called_another_way_is_refused_in_python_s_words() -> None:
    config, _ = tracked({"a": 1})
    python: dict[str, int] = {"a": 1}

    for call in (
        lambda d: d.get(),
        lambda d: d.get("a", 1, 2),
        lambda d: d.get(key="a"),
        lambda d: d.keys(1),
        lambda d: d.update(1, 2),
        lambda d: d.popitem(1),
    ):
        with pytest.raises(TypeError) as expected:
            call(python)
        with pytest.raises(TypeError, match=re.escape(str(expected.value))):
            call(config)


def test_popitem_on_an_empty_dict_raises_after_its_fork() -> None:
    config, sink = tracked({})

    with pytest.raises(KeyError) as raised:
        config.popitem()

    assert raised_by_target(raised.value)
    assert forks(sink) == [(["!=", ["len", "config"], 0], False)]


def test_a_plain_dict_s_operations_are_python_s_own() -> None:
    config, sink = tracked({"a": 1})
    config.clear()

    config["a"] = 1
    assert config.popitem() == ("a", 1)
    config["a"] = 1
    config.update(b=2)
    assert config.pop("a") == 1 and config.setdefault("c", 3) == 3
    assert config.copy() == {"b": 2, "c": 3} and config | {"d": 4} == {"b": 2, "c": 3, "d": 4}
    assert {"d": 4} | config == {"d": 4, "b": 2, "c": 3}
    assert config == {"b": 2, "c": 3} and len(config) == 2
    assert list(config.items()) == [("b", 2), ("c", 3)]
    assert list(reversed(config)) == ["c", "b"]
    del config["b"]
    assert copy.deepcopy(config) == {"c": 3} and bound.len(config) == 1

    assert forks(sink) == [] and downgrades(sink) == []


def test_a_tracked_dict_is_a_dict_kind_to_a_list() -> None:
    config, _ = tracked({})

    assert kind_of(config) == "dict"
    assert kind_of(ConcolicList.made([], "items", [])) == "list"


def test_fromkeys_answers_as_dict_s_own() -> None:
    config, sink = tracked({"a": 1})

    made = config.fromkeys(["x"], 0)

    assert made == {"x": 0} and type(made) is dict and sink == []


def test_every_other_dict_method_is_a_downgrade() -> None:
    config, sink = tracked({"a": 1})

    assert str(config) == "{'a': 1}"
    assert f"{config}" == "{'a': 1}"
    assert config.__lt__({}) is NotImplemented

    # an f-string with no format spec asks `__str__` through `__format__`, as for an int
    assert downgrades(sink) == ["__str__", "__str__", "__format__"]


def test_popitem_hands_out_a_key_the_target_added_as_it_is() -> None:
    config, sink = tracked({"a": 1})

    config["n"] = 2
    assert config.popitem() == ("n", 2)
    assert bool(config)

    assert forks(sink)[-1] == (["!=", ["len", "config"], 0], True)


def test_popitem_notices_a_last_value_changed_without_the_methods() -> None:
    config, sink = tracked({"a": 1, "b": 2})

    dict.__setitem__(config, "b", 9)
    assert config.popitem() == ("b", 9)

    assert downgrades(sink) == ["popitem"]
    assert bool(config) and len(forks(sink)) == 1


def test_a_key_of_another_kind_the_dict_holds_is_not_stored_again() -> None:
    config, sink = tracked({"a": 1})

    config[(1, 2)] = 3
    assert config.setdefault((1, 2), 9) == 3
    merged = {(5, 6): 0, "a": 7} | config

    assert list(merged) == [(5, 6), "a", (1, 2)] and merged["a"] == 1
    assert bool(merged)
    assert forks(sink)[-1] == (["!=", ["+", ["len", "config"], 2], 0], True)
    assert downgrades(sink) == ["__setitem__", "setdefault", "__ror__"]


def test_a_tracked_key_hands_out_a_str_value_tracked_and_any_other_as_it_is() -> None:
    config, sink = tracked({"s": "x", "rows": [1]})
    name = ConcolicStr.made("s", "name", sink)
    rows = ConcolicStr.made("rows", "name", sink)

    read = config[name]
    assert type(read) is ConcolicStr and read.expression == ["[]", "config", "name"]
    assert config[rows] == [1] and type(config[rows]) is list


def test_a_view_of_a_plain_dict_is_python_s_own() -> None:
    config, sink = tracked({"a": 1})
    config.clear()
    config["a"] = 1

    assert config.keys() & {"a"} == {"a"} and (1, 2) not in config
    assert ("z", 1) not in config.items() and config.keys().__eq__(5) is NotImplemented
    assert pickle.loads(pickle.dumps(config)) == {"a": 1}

    assert downgrades(sink) == [] and forks(sink) == []


def test_an_item_whose_key_the_dict_lacks_is_not_in_its_items() -> None:
    config, sink = tracked({"a": 1})

    assert ("z", 1) not in config.items()

    assert forks(sink) == [(["in", "'z'", "config"], False)]


def test_every_method_of_dict_is_taught_kept_or_a_downgrade() -> None:
    # the class body teaches, `_KEPT` keeps, and the derivation downgrades the rest: no method
    # of dict is left to answer silently as dict's own
    kept = {
        "__new__",
        "__init__",
        "__repr__",
        "__getattribute__",
        "__sizeof__",
        "__class_getitem__",
    }
    methods = {name for name, member in vars(dict).items() if callable(member)}
    assert methods - set(vars(ConcolicDict)) <= kept


@pytest.mark.parametrize("view", [ConcolicKeys, ConcolicValues, ConcolicItems])
def test_every_method_of_a_view_is_taught_or_a_downgrade(view: type) -> None:
    python = type(view.python({}))
    methods = {name for name, member in vars(python).items() if callable(member)}
    taught = set(vars(view)) | set(vars(view.__mro__[1]))
    assert methods - taught <= {"__new__", "__getattribute__", "__sizeof__", "__hash__"}


def test_setdefault_under_a_tracked_key_into_a_changed_dict_is_named_once() -> None:
    config, sink = tracked({"a": 1})
    config["n"] = 2
    name = ConcolicStr.made("b", "name", sink)

    assert config.setdefault(name, 5) == 5

    assert downgrades(sink) == ["setdefault"]
    assert plain_dict(config) == {"a": 1, "n": 2, "b": 5}


@pytest.mark.parametrize("view", ["keys", "values", "items"])
def test_a_view_turned_into_text_is_named_as_the_dict_is(view: str) -> None:
    config, sink = tracked({"a": 1})
    python = getattr({"a": 1}, view)()
    shown = getattr(config, view)()

    assert str(shown) == str(python) and f"{shown}" == f"{python}"
    # repr is the debugger's path, not the target's, and stays Python's as the dict's does
    assert repr(shown) == repr(python)

    assert downgrades(sink) == ["__str__", "__format__"]


def test_the_size_term_follows_every_change_as_it_happens() -> None:
    config, sink = tracked({"a": 1, "b": 2})
    name = ConcolicStr.made("x", "name", sink)

    config["n"] = 1
    config["a"] = 5
    del config["b"]
    config.pop("n")
    config.setdefault("m", 0)
    config.update(p=1, a=2)
    config[name] = 3
    config.popitem()
    merged = {"q": 0, "a": 9} | config
    copied = config.copy()
    copied["r"] = 1

    for made in (config, merged, copied):
        grown = dict.__len__(made) - 2
        written: Expression = ["len", "config"]
        if grown:
            written = ["+", written, grown] if grown > 0 else ["-", written, -grown]
        assert made.size_term() == written, made


def test_a_walk_after_many_stores_writes_its_size_at_once() -> None:
    config, _ = tracked({"a": 1})
    for n in range(10_000):
        config[f"k{n}"] = n

    started = time.monotonic()
    assert sum(1 for _ in config) == 10_001
    # the scan measured 6.96 s here when each fork summed every change
    assert time.monotonic() - started < 2.0

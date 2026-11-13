"""A plain dict's key ``"__class__"`` written ``"!__class__"`` in seed JSON: the codec, and the
walks that read the escape (bind, the seed's leaves) or write it again (``Seed.of``, ``apply``)."""

import json
from collections import OrderedDict

import pytest

from pyct.binding.annotations import Builds, Fields, Items
from pyct.binding.bind import Seed, bind, leaves
from pyct.binding.model import apply
from pyct.binding.seed_keys import read_key, written_key
from pyct.binding.shapes import DictAnswer
from pyct.core.dicts.dicts import ConcolicDict
from pyct.core.numbers.ints import ConcolicInt
from tests.unit.binding.named_classes import Point

CLASS_AT_D = json.dumps(["[]", "d", "'__class__'"])


def keys(value: object) -> list[object]:
    """A dict's keys, in order."""
    assert isinstance(value, dict), value
    return list(value)


@pytest.mark.parametrize(
    ("written", "read"),
    [
        ("!__class__", "__class__"),
        ("!!__class__", "!__class__"),
        ("!!!__class__", "!!__class__"),
    ],
)
def test_an_escaped_key_reads_one_bang_fewer_and_writes_back(written: str, read: str) -> None:
    assert read_key(written) == read
    assert written_key(read) == written


@pytest.mark.parametrize(
    "key", ["a", "__args__", "!__args__", "!", "!!", "__class__!", "!_class__", "", 3, None]
)
def test_any_other_key_reads_and_writes_as_it_is(key: object) -> None:
    assert read_key(key) == key
    assert written_key(key) == key


def test_a_str_subclass_key_is_never_escaped() -> None:
    class Name(str):
        pass

    key = Name("__class__")

    assert written_key(key) is key
    assert read_key(Name("!__class__")) == "!__class__"


def test_bind_hands_the_target_the_key_as_read_and_tracks_it_by_that_key() -> None:
    args = bind({"d": {"!__class__": 1, "a": 2, "!!__class__": 3}}, [])

    d = args["d"]
    assert isinstance(d, ConcolicDict)
    assert list(d) == ["__class__", "a", "!__class__"]
    value = d["__class__"]
    assert isinstance(value, ConcolicInt) and value.expression == ["[]", "d", "'__class__'"]


def test_a_seed_keeps_the_escape_and_names_its_leaves_and_dict_by_the_read_key() -> None:
    seed = Seed.of({"d": {"!__class__": 1, "a": 2}})

    assert seed.args == {"d": {"!__class__": 1, "a": 2}}
    assert list(seed.leaves) == [CLASS_AT_D, json.dumps(["[]", "d", "'a'"])]
    assert seed.dicts["d"].keys == ("__class__", "a")
    assert list(leaves({"d": {"!__class__": 1}})) == [CLASS_AT_D]


def test_an_answer_writes_the_key_the_solver_adds_escaped() -> None:
    origin = Seed.of({"d": {"a": 1}})

    answered = apply(origin, {"d": DictAnswer(present={"__class__": True}, kept=1)})

    assert answered.args == {"d": {"a": 1, "!__class__": 0}}
    assert answered.dicts["d"].keys == ("a", "__class__")
    assert apply(answered, {CLASS_AT_D: 7}).args == {"d": {"a": 1, "!__class__": 7}}


def test_an_answer_writes_an_escaped_key_the_solver_adds_with_one_bang_more() -> None:
    origin = Seed.of({"d": {"a": 1}})

    answered = apply(origin, {"d": DictAnswer(present={"!__class__": True}, kept=1)})

    assert answered.args == {"d": {"a": 1, "!!__class__": 0}}


def test_a_dict_reached_by_two_paths_is_one_copy_in_each_spelling() -> None:
    shared = {"!__class__": 1}

    copied = Seed.of({"a": shared, "b": shared}).args
    bound = bind({"a": shared, "b": shared}, [])

    assert copied["a"] is copied["b"] and copied["a"] == {"!__class__": 1}
    assert bound["a"] is bound["b"] and keys(bound["a"]) == ["__class__"]


def test_a_dict_first_reached_under_no_name_reads_its_escape_when_a_later_path_names_it() -> None:
    inner = {"!__class__": 1}
    seed: dict[str, object] = {"m": {1.5: inner}, "n": inner}

    copied = Seed.of(seed)
    bound = bind(seed, [])

    assert copied.args["n"] == {"!__class__": 1}
    m = copied.args["m"]
    assert isinstance(m, dict) and m[1.5] is copied.args["n"]
    assert json.dumps(["[]", "n", "'__class__'"]) in copied.leaves
    n = bound["n"]
    assert isinstance(n, dict) and list(n) == ["__class__"]
    assert n["__class__"].expression == ["[]", "n", "'__class__'"]


def test_a_plain_copy_reads_and_writes_the_escape_like_a_tracked_dict() -> None:
    # a dict that holds an object form is a plain copy of fixed keys
    seed = {"box": {"!__class__": 0, "b": {"__class__": "Point", "x": 1, "y": 2}}}

    copied = Seed.of(seed).args
    bound = bind(seed, [])

    assert copied == seed
    box = bound["box"]
    assert type(box) is dict and list(box) == ["__class__", "b"]


def test_a_dict_inside_a_tuple_holding_the_class_key_is_written_escaped() -> None:
    copied = Seed.of({"t": ({"__class__": 1},)}).args
    bound = bind({"t": ({"!__class__": 1},)}, [])

    assert copied == {"t": ({"!__class__": 1},)}
    t = bound["t"]
    assert isinstance(t, tuple) and keys(t[0]) == ["__class__"]


def test_an_int_keyed_dict_reads_both_an_int_s_text_and_the_escape() -> None:
    checks = {"d": Items(dict, None, int)}

    bound = bind({"d": {"3": 1, "!__class__": 2}}, [], checks)
    copied = Seed.of({"d": {"3": 1, "!__class__": 2}}, checks).args

    assert keys(bound["d"]) == [3, "__class__"]
    assert copied == {"d": {3: 1, "!__class__": 2}}


@pytest.mark.parametrize(
    ("seed", "checks"),
    [
        ({"d": {"__class__": "Point", "x": 1, "y": 2, "!__class__": 0}}, None),
        ({"d": {"x": 1, "y": 2, "!__class__": 0}}, {"d": Builds(Point)}),
        ({"d": {"x": 1, "!__class__": 0}}, {"d": Fields({})}),
    ],
    ids=["object form", "hinted dict", "self"],
)
def test_a_constructor_s_keys_are_never_read_or_written(
    seed: dict[str, dict[str, object]], checks: dict[str, Fields | Builds] | None
) -> None:
    bound = bind(seed, [], checks)
    copied = Seed.of(seed, checks).args

    assert keys(bound["d"]) == keys(seed["d"])
    assert copied == seed


def test_a_dict_subclass_keeps_its_keys() -> None:
    seed = {"d": OrderedDict([("!__class__", 1), ("__class__", 2)])}

    bound = bind(seed, [])
    copied = Seed.of(seed).args

    assert keys(bound["d"]) == ["!__class__", "__class__"]
    assert keys(copied["d"]) == ["!__class__", "__class__"]

"""An object form the walk keeps the shape of: a dict with ``"__class__"`` at a place pyct builds
an object at, its keys fixed, its ``"__args__"`` a list of fixed length, its values named."""

import json
from typing import Any, cast

from pyct.binding.annotations import Fields, Items
from pyct.binding.bind import Seed, bind, leaves
from pyct.binding.model import apply
from pyct.core.numbers.ints import ConcolicInt
from pyct.core.strs.strs import ConcolicStr

C_NAME = json.dumps(["[]", "c", "'name'"])
C_AGE = json.dumps(["[]", "c", "'age'"])
P_FIRST = json.dumps(["[]", ["[]", "p", "'__args__'"], 0])
P_Y = json.dumps(["[]", "p", "'y'"])
CUSTOMER = {"__class__": "Customer", "name": "ann", "age": 30}
POINT = {"__class__": "Point", "__args__": [1], "y": 2}
SELF = {"self": Fields({})}


def test_a_parameter_s_object_form_is_a_plain_dict_whose_values_are_leaves() -> None:
    seed = Seed.of({"c": CUSTOMER})

    assert seed.args == {"c": CUSTOMER}
    assert type(seed.args["c"]) is dict
    # "__class__" is no value: it is never named
    assert seed.leaves == {C_NAME: str, C_AGE: int}
    assert seed.dicts == {}
    assert leaves({"c": CUSTOMER}) == {C_NAME: str, C_AGE: int}


def test_args_items_are_leaves_in_a_plain_list_of_fixed_length() -> None:
    seed = Seed.of({"p": POINT})

    assert seed.leaves == {P_FIRST: int, P_Y: int}
    assert seed.lists == {}


def test_bind_tracks_the_values_and_leaves_class_and_args_plain() -> None:
    args: dict[str, Any] = bind({"p": POINT}, [])

    point = args["p"]
    assert type(point) is dict and list(point) == ["__class__", "__args__", "y"]
    assert type(point["__class__"]) is str
    assert type(point["__args__"]) is list
    first = point["__args__"][0]
    assert isinstance(first, ConcolicInt)
    assert first.expression == ["[]", ["[]", "p", "'__args__'"], 0]


def test_an_answer_comes_back_in_the_seed_s_shape() -> None:
    origin = Seed.of({"p": POINT})

    answered = apply(origin, {P_FIRST: 7})

    assert answered.args == {"p": {"__class__": "Point", "__args__": [7], "y": 2}}
    assert answered.leaves == origin.leaves


def test_an_object_form_inside_one_is_one_too() -> None:
    order = {"__class__": "Order", "customer": CUSTOMER, "total": 5}

    seed = Seed.of({"o": order})

    assert seed.dicts == {}
    assert seed.leaves == {
        json.dumps(["[]", ["[]", "o", "'customer'"], "'name'"]): str,
        json.dumps(["[]", ["[]", "o", "'customer'"], "'age'"]): int,
        json.dumps(["[]", "o", "'total'"]): int,
    }


def test_an_object_form_among_args_items_is_one_too() -> None:
    seed = Seed.of({"p": {"__class__": "Pair", "__args__": [CUSTOMER]}})

    assert seed.dicts == {}
    first = ["[]", ["[]", "p", "'__args__'"], 0]
    assert seed.leaves == {
        json.dumps(["[]", first, "'name'"]): str,
        json.dumps(["[]", first, "'age'"]): int,
    }


def test_a_list_or_dict_under_an_object_form_is_tracked_as_any_argument_s() -> None:
    seed = Seed.of({"c": {"__class__": "Customer", "tags": ["a"], "notes": {"k": 1}}})

    assert list(seed.lists) == [json.dumps(["[]", "c", "'tags'"])]
    assert list(seed.dicts) == [json.dumps(["[]", "c", "'notes'"])]


def test_args_that_is_not_a_list_is_never_tracked() -> None:
    seed = Seed.of({"c": {"__class__": "Customer", "__args__": "ann", "age": 30}})

    assert seed.leaves == {C_AGE: int}


def test_an_object_form_directly_under_a_built_instance_s_fields_is_one() -> None:
    seed = Seed.of({"self": {"owner": CUSTOMER}}, SELF)

    owner = ["[]", "self", "'owner'"]
    assert seed.dicts == {}
    assert seed.leaves == {
        json.dumps(["[]", owner, "'name'"]): str,
        json.dumps(["[]", owner, "'age'"]): int,
    }


def test_class_directly_under_a_built_instance_s_fields_stays_a_key() -> None:
    seed = Seed.of({"self": {"__class__": "Shop", "owner": "ann"}}, SELF)

    assert seed.leaves == {
        json.dumps(["[]", "self", "'__class__'"]): str,
        json.dumps(["[]", "self", "'owner'"]): str,
    }


def test_a_list_or_dict_that_holds_a_form_keeps_its_shape_and_names_its_values() -> None:
    seed = Seed.of({"rows": [{"c": dict(CUSTOMER)}, 5], "d": {"ann": dict(CUSTOMER)}})

    assert seed.lists == {} and seed.dicts == {}
    assert seed.args == {"rows": [{"c": CUSTOMER}, 5], "d": {"ann": CUSTOMER}}
    c = ["[]", ["[]", "rows", 0], "'c'"]
    ann = ["[]", "d", "'ann'"]
    assert seed.leaves == {
        json.dumps(["[]", c, "'name'"]): str,
        json.dumps(["[]", c, "'age'"]): int,
        json.dumps(["[]", "rows", 1]): int,
        json.dumps(["[]", ann, "'name'"]): str,
        json.dumps(["[]", ann, "'age'"]): int,
    }
    assert leaves({"rows": [{"c": dict(CUSTOMER)}, 5]}) == {
        name: kind for name, kind in seed.leaves.items() if "rows" in name
    }


def test_a_list_beside_a_form_holding_none_is_tracked_by_its_place() -> None:
    seed = Seed.of({"cs": [dict(CUSTOMER), ["x"], {"k": 1}]})

    assert list(seed.lists) == [json.dumps(["[]", "cs", 1])]
    assert list(seed.dicts) == [json.dumps(["[]", "cs", 2])]


def test_bind_copies_a_list_that_holds_a_form_plain() -> None:
    args: dict[str, Any] = bind({"cs": [dict(CUSTOMER), 5]}, [])

    cs = args["cs"]
    assert type(cs) is list and type(cs[0]) is dict
    assert isinstance(cs[1], ConcolicInt) and cs[1].expression == ["[]", "cs", 1]


def test_the_annotation_of_a_list_that_holds_a_form_still_reads_its_items() -> None:
    checks = {"cs": Items(list, Items(dict, int, keys=int)), "d": Items(dict, None, keys=int)}
    seed = Seed.of({"cs": [dict(CUSTOMER), {"1": 2}], "d": {"3": dict(CUSTOMER)}}, checks)

    assert seed.dicts[json.dumps(["[]", "cs", 1])].keys == (1,)
    assert list(cast(dict[object, object], seed.args["d"])) == [3]
    assert json.dumps(["[]", ["[]", "d", 3], "'age'"]) in seed.leaves


def test_an_answer_keeps_the_shape_around_a_form() -> None:
    origin = Seed.of({"cs": [dict(CUSTOMER)], "d": {"ann": dict(CUSTOMER)}})
    age = json.dumps(["[]", ["[]", "cs", 0], "'age'"])

    answered = apply(origin, {age: 70})

    assert answered.args == {"cs": [{**CUSTOMER, "age": 70}], "d": {"ann": CUSTOMER}}
    assert answered.leaves == origin.leaves


def test_a_form_under_a_key_no_access_names_is_kept_untracked() -> None:
    seed = Seed.of({"d": {2.5: dict(CUSTOMER)}})

    assert seed.args == {"d": {2.5: CUSTOMER}}
    assert seed.leaves == {} and seed.dicts == {}


def test_a_dict_with_class_inside_a_tuple_or_an_object_stays_a_tracked_dict() -> None:
    class Holder:
        def __init__(self) -> None:
            self.d = dict(CUSTOMER)

    named = leaves({"t": (dict(CUSTOMER),), "o": Holder()})

    assert json.dumps(["[]", ["[]", "t", 0], "'__class__'"]) in named
    assert json.dumps(["[]", ["getattr", "o", "'d'"], "'__class__'"]) in named


def test_a_list_under_fields_keeps_its_length_and_its_items_are_leaves() -> None:
    seed = Seed.of({"xs": [1, "a"]}, {"xs": Fields({})})

    assert seed.lists == {}
    assert seed.leaves == {json.dumps(["[]", "xs", 0]): int, json.dumps(["[]", "xs", 1]): str}


def test_bind_names_a_value_of_an_object_form_by_its_key() -> None:
    args: dict[str, Any] = bind({"c": CUSTOMER}, [])

    name = args["c"]["name"]
    assert isinstance(name, ConcolicStr)
    assert name.expression == ["[]", "c", "'name'"]

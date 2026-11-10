"""A JSON object or list under a class hint: a plain copy of fixed shape, its values named by
their places and checked by the constructor's own hints."""

import json

from pyct.binding.annotations import Builds, Fields, Items, NoOneClass
from pyct.binding.bind import Seed, bind, leaves
from pyct.binding.model import apply
from pyct.core.foundation.branch import Expression, SinkItem
from pyct.core.numbers.ints import ConcolicInt
from tests.unit.binding.hint_classes import Basket, Shape, Spot
from tests.unit.binding.named_classes import Point

POINT = {"p": Builds(Point)}


def named(*steps: object) -> str:
    """The leaf name of the access ``steps`` writes from a parameter."""
    access: Expression = str(steps[0])
    for key in steps[1:]:
        access = ["[]", access, key if isinstance(key, int) else repr(key)]
    return json.dumps(access)


def test_a_hinted_dict_is_a_plain_copy_whose_values_are_leaves() -> None:
    seed = Seed.of({"p": {"x": 1, "y": 2}}, POINT)

    assert seed.args == {"p": {"x": 1, "y": 2}}
    assert type(seed.args["p"]) is dict
    assert seed.leaves == {named("p", "x"): int, named("p", "y"): int}
    assert seed.dicts == {}


def test_a_hinted_list_keeps_its_length_and_its_items_are_leaves() -> None:
    seed = Seed.of({"p": [1, 2]}, POINT)

    assert seed.args == {"p": [1, 2]}
    assert seed.leaves == {named("p", 0): int, named("p", 1): int}
    assert seed.lists == {}


def test_args_in_a_hinted_dict_keeps_its_length() -> None:
    seed = Seed.of({"p": {"__args__": [1], "y": 2}}, POINT)

    assert seed.leaves == {named("p", "__args__", 0): int, named("p", "y"): int}
    assert seed.lists == {}


def test_a_hinted_value_inside_takes_its_constructor_s_hint() -> None:
    seed = Seed.of({"s": {"at": {"x": 1, "y": 2}, "label": "a"}}, {"s": Builds(Spot)})

    assert seed.dicts == {}
    assert seed.leaves == {
        named("s", "at", "x"): int,
        named("s", "at", "y"): int,
        named("s", "label"): str,
    }


def test_a_hinted_list_s_items_take_the_hints_at_their_positions() -> None:
    seed = Seed.of({"s": [{"x": 1, "y": 2}, "a"]}, {"s": Builds(Spot)})

    assert seed.dicts == {}
    assert seed.leaves == {named("s", 0, "x"): int, named("s", 0, "y"): int, named("s", 1): str}


def test_args_items_take_the_hints_at_their_positions() -> None:
    seed = Seed.of({"s": {"__args__": [{"x": 1, "y": 2}]}}, {"s": Builds(Spot)})

    assert seed.dicts == {}
    assert list(seed.leaves) == [named("s", "__args__", 0, "x"), named("s", "__args__", 0, "y")]


def test_a_class_dict_under_a_class_hint_keeps_its_shape_and_class_is_no_leaf() -> None:
    seed = Seed.of({"p": {"__class__": "Point", "x": 1, "y": 2}}, POINT)

    assert seed.args == {"p": {"__class__": "Point", "x": 1, "y": 2}}
    assert seed.leaves == {named("p", "x"): int, named("p", "y"): int}
    assert seed.dicts == {}


def test_an_object_under_a_hint_that_names_no_one_class_keeps_its_shape() -> None:
    seed = Seed.of(
        {"s": {"side": 1}, "t": [1]},
        {"s": NoOneClass("r", (Shape,)), "t": NoOneClass("r", (Shape,))},
    )

    assert seed.leaves == {named("s", "side"): int, named("t", 0): int}
    assert seed.dicts == {}
    assert seed.lists == {}


def test_a_null_and_a_scalar_under_a_class_hint_pass_as_they_are() -> None:
    seed = Seed.of({"p": None, "q": "blue"}, {"p": Builds(Point), "q": Builds(Point)})

    assert seed.args == {"p": None, "q": "blue"}
    assert seed.leaves == {"q": str}


def test_a_hinted_field_of_a_built_instance_keeps_its_shape() -> None:
    checks = {"self": Fields({"owner": Builds(Point)})}
    seed = Seed.of({"self": {"owner": {"x": 1, "y": 2}}}, checks)

    assert seed.dicts == {}
    assert list(seed.leaves) == [
        json.dumps(["[]", ["[]", "self", "'owner'"], "'x'"]),
        json.dumps(["[]", ["[]", "self", "'owner'"], "'y'"]),
    ]


def test_a_list_hint_beside_still_reads_its_items() -> None:
    seed = Seed.of({"p": {"x": 1, "y": 2}, "xs": []}, {**POINT, "xs": Items(list, int)})

    assert seed.lists["xs"].fill == "int"


def test_bind_copies_a_hinted_dict_and_list_plain_and_tracks_their_values() -> None:
    sink: list[SinkItem] = []

    args = bind({"p": {"x": 1, "y": 2}, "q": [3, 4]}, sink, {**POINT, "q": Builds(Point)})

    p, q = args["p"], args["q"]
    assert type(p) is dict and type(q) is list
    x, at = p["x"], q[1]  # pyrefly: ignore[bad-index]
    assert isinstance(x, ConcolicInt) and x.expression == ["[]", "p", "'x'"]
    assert isinstance(at, ConcolicInt) and at.expression == ["[]", "q", 1]


def test_an_answer_comes_back_in_the_seed_s_shape() -> None:
    origin = Seed.of({"p": [1, 2], "s": {"at": {"x": 1, "y": 2}}}, {**POINT, "s": Builds(Spot)})

    answered = apply(origin, {named("p", 0): 9, named("s", "at", "y"): 7})

    assert answered.args == {"p": [9, 2], "s": {"at": {"x": 1, "y": 7}}}
    assert answered.leaves == origin.leaves
    assert answered.checks == origin.checks


def test_leaves_name_a_hinted_value_by_the_same_access() -> None:
    seed = Seed.of({"p": [1, 2]}, POINT)

    assert set(seed.leaves) <= set(leaves(seed.args))


HOME = "tests.unit.binding.hint_classes"


def test_a_named_object_s_values_take_its_constructor_s_hints_in_every_walk() -> None:
    args = {"o": {"__class__": "Spot", "at": {"x": 1, "y": 2}}}
    sink: list[SinkItem] = []

    seed = Seed.of(args, {}, HOME)
    answered = apply(seed, {named("o", "at", "x"): 5})
    at = bind(args, sink, {}, HOME)["o"]["at"]  # pyrefly: ignore[bad-index]

    assert seed.dicts == {} and answered.dicts == {}
    assert answered.args == {"o": {"__class__": "Spot", "at": {"x": 5, "y": 2}}}
    assert type(at) is dict


def test_a_named_class_that_does_not_load_asks_nothing() -> None:
    seed = Seed.of({"o": {"__class__": "Nowhere", "at": {"x": 1}}}, {}, HOME)

    assert list(seed.dicts) == [named("o", "at")]


def test_a_named_object_s_hints_read_int_keys_and_say_an_added_item_s_kind() -> None:
    seed = Seed.of({"o": {"__class__": "Counts", "by": {"3": 1}, "tags": []}}, {}, HOME)

    assert seed.args == {"o": {"__class__": "Counts", "by": {3: 1}, "tags": []}}
    assert seed.lists[named("o", "tags")].fill == "str"


ITEMS = {"items": Items(list, Builds(Point), fixed=True)}
BY = {"by": Items(dict, Builds(Point), fixed=True)}


def test_a_list_of_a_class_keeps_its_length_and_its_items_values_are_leaves() -> None:
    seed = Seed.of({"items": [{"x": 1, "y": 2}, [3, 4]]}, ITEMS)

    assert seed.args == {"items": [{"x": 1, "y": 2}, [3, 4]]}
    assert type(seed.args["items"]) is list
    assert seed.lists == {} and seed.dicts == {}
    assert seed.leaves == {
        named("items", 0, "x"): int,
        named("items", 0, "y"): int,
        named("items", 1, 0): int,
        named("items", 1, 1): int,
    }


def test_a_dict_of_a_class_keeps_its_keys_and_its_values_values_are_leaves() -> None:
    seed = Seed.of({"by": {"a": {"x": 1, "y": 2}}}, BY)

    assert seed.args == {"by": {"a": {"x": 1, "y": 2}}}
    assert seed.lists == {} and seed.dicts == {}
    assert seed.leaves == {named("by", "a", "x"): int, named("by", "a", "y"): int}


def test_an_empty_list_or_dict_of_a_class_stays_empty_and_untracked() -> None:
    seed = Seed.of({"items": [], "by": {}}, {**ITEMS, **BY})

    assert seed.args == {"items": [], "by": {}}
    assert seed.leaves == {} and seed.lists == {} and seed.dicts == {}


def test_null_and_a_scalar_in_a_list_of_a_class_pass_and_a_scalar_is_a_leaf() -> None:
    seed = Seed.of({"items": [None, 5, "s"]}, ITEMS)

    assert seed.args == {"items": [None, 5, "s"]}
    assert seed.leaves == {named("items", 1): int, named("items", 2): str}


def test_a_list_of_lists_of_a_class_is_fixed_at_every_level() -> None:
    inner = Items(list, Builds(Point), fixed=True)
    seed = Seed.of({"rows": [[{"x": 1, "y": 2}], []]}, {"rows": Items(list, inner, fixed=True)})

    assert seed.lists == {} and seed.dicts == {}
    assert seed.leaves == {named("rows", 0, 0, "x"): int, named("rows", 0, 0, "y"): int}


def test_a_list_of_a_class_under_a_constructor_s_hint_is_fixed() -> None:
    seed = Seed.of(
        {"b": {"items": [{"x": 1, "y": 2}], "by": {}, "tags": []}}, {"b": Builds(Basket)}
    )

    assert seed.dicts == {}
    assert list(seed.lists) == [named("b", "tags")]
    assert seed.leaves == {named("b", "items", 0, "x"): int, named("b", "items", 0, "y"): int}


def test_a_list_of_a_class_inside_a_named_object_is_fixed() -> None:
    args = {"o": {"__class__": "Basket", "items": [{"x": 1, "y": 2}], "by": {}, "tags": []}}

    seed = Seed.of(args, {}, HOME)

    assert list(seed.lists) == [named("o", "tags")]
    assert list(seed.leaves) == [named("o", "items", 0, "x"), named("o", "items", 0, "y")]


def test_an_answer_keeps_a_list_and_dict_of_a_class_in_the_seed_s_shape() -> None:
    origin = Seed.of({"items": [{"x": 1, "y": 2}], "by": {"a": [1, 2]}}, {**ITEMS, **BY})

    answered = apply(origin, {named("items", 0, "x"): 9, named("by", "a", 1): 7})

    assert answered.args == {"items": [{"x": 9, "y": 2}], "by": {"a": [1, 7]}}
    assert answered.leaves == origin.leaves
    assert answered.lists == {} and answered.dicts == {}


def test_bind_copies_a_list_and_dict_of_a_class_plain_and_tracks_their_values() -> None:
    sink: list[SinkItem] = []

    args = bind({"items": [{"x": 1, "y": 2}], "by": {"a": [3, 4]}}, sink, {**ITEMS, **BY})

    items, by = args["items"], args["by"]
    assert type(items) is list and type(by) is dict
    assert type(items[0]) is dict and type(by["a"]) is list  # pyrefly: ignore[bad-index]
    x, at = items[0]["x"], by["a"][1]  # pyrefly: ignore[bad-index]
    assert isinstance(x, ConcolicInt) and x.expression == ["[]", ["[]", "items", 0], "'x'"]
    assert isinstance(at, ConcolicInt) and at.expression == ["[]", ["[]", "by", "'a'"], 1]


def test_leaves_name_a_list_of_a_class_s_values_by_the_same_access() -> None:
    seed = Seed.of({"items": [{"x": 1, "y": 2}], "by": {"a": [3, 4]}}, {**ITEMS, **BY})

    assert set(seed.leaves) <= set(leaves(seed.args))


def test_instances_in_a_list_of_a_class_are_followed_by_their_attributes() -> None:
    caller = Point(1, 2)
    seed = Seed.of({"items": [caller]}, ITEMS)

    copied = seed.args["items"][0]  # pyrefly: ignore[bad-index]
    assert type(copied) is Point and copied is not caller
    assert seed.lists == {}
    assert list(seed.leaves) == [
        json.dumps(["getattr", ["[]", "items", 0], "'x'"]),
        json.dumps(["getattr", ["[]", "items", 0], "'y'"]),
    ]

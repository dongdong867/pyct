"""A JSON object or list under a class hint: a plain copy of fixed shape, its values named by
their places and checked by the constructor's own hints."""

import json

from pyct.binding.annotations import Builds, Fields, Items, NoOneClass
from pyct.binding.bind import Seed, bind, leaves
from pyct.binding.model import apply
from pyct.core.foundation.branch import Expression, SinkItem
from pyct.core.numbers.ints import ConcolicInt
from tests.unit.binding.hint_classes import Spot
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
    seed = Seed.of({"s": {"side": 1}, "t": [1]}, {"s": NoOneClass("r"), "t": NoOneClass("r")})

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

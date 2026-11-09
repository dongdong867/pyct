"""The objects a class hint builds: listed at their places, at every level the constructors'
hints reach, and planned as the call builds them."""

import pytest

from pyct.binding.annotations import Builds, Fields, NoOneClass, contradictions
from pyct.binding.builds import BuildError, object_forms, plan_call
from tests.unit.binding.hint_classes import Spot
from tests.unit.binding.named_classes import Holder, Point

HOME = "tests.unit.binding.hint_classes"
SPOT = {"s": Builds(Spot)}


def test_a_dict_a_hint_builds_is_listed_with_the_ones_its_constructor_s_hints_build() -> None:
    args = {"s": {"at": {"x": 1, "y": 2}, "label": "a"}}

    found = object_forms(args, None, SPOT, HOME).found

    assert [(each.place, each.check) for each in found] == [
        ("s['at']", Builds(Point)),
        ("s", Builds(Spot)),
    ]


def test_no_checks_list_only_the_dicts_that_name_their_class() -> None:
    assert object_forms({"s": {"at": {"x": 1, "y": 2}}}, None).found == ()


def test_a_named_object_s_values_take_its_constructor_s_hints() -> None:
    named = {"__class__": "Spot", "at": {"x": 1, "y": 2}}

    found = object_forms({"o": named}, None, {}, HOME).found

    assert [each.place for each in found] == ["o['at']", "o"]


def test_a_named_object_whose_class_does_not_load_asks_nothing() -> None:
    named = {"__class__": "Nowhere", "at": {"x": 1, "y": 2}}

    assert [each.place for each in object_forms({"o": named}, None, {}, HOME).found] == ["o"]


def test_a_hinted_field_of_self_is_listed() -> None:
    args = {"self": {"owner": {"x": 1, "y": 2}}}
    checks = {"self": Fields({"owner": Builds(Point)})}

    assert [each.place for each in object_forms(args, "self", checks, HOME).found] == [
        "self['owner']"
    ]


def test_the_plan_calls_the_hint_s_class_at_every_level() -> None:
    args = {"s": {"at": {"x": 1, "y": 2}, "label": "a"}}

    plan = plan_call(args, (), None, HOME, SPOT)

    assert [(build.cls, build.place) for build in plan.builds] == [(Point, "s['at']"), (Spot, "s")]
    assert plan.builds[1].keywords == {"at": args["s"]["at"], "label": "a"}


def test_a_named_class_wins_over_the_hint() -> None:
    args = {"s": {"__class__": "tests.unit.binding.named_classes::Holder", "inner": 1}}

    plan = plan_call(args, (), None, HOME, SPOT)

    assert [build.cls for build in plan.builds] == [Holder]


def test_a_hint_that_names_no_one_class_is_the_build_error() -> None:
    with pytest.raises(BuildError) as raised:
        plan_call({"s": {"side": 1}}, (), None, HOME, {"s": NoOneClass("the reason")})

    assert (raised.value.place, raised.value.reason) == ("s", "the reason")


def test_a_hinted_value_gives_no_type_line() -> None:
    checks = {"p": Builds(Point), "s": NoOneClass("r"), "self": Fields({"o": Builds(Point)})}
    seed = {"p": {"x": "1"}, "s": [1], "self": {"o": "x"}}

    assert contradictions(checks, seed) == []

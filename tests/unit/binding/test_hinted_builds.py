"""The objects a class hint builds: listed at their places, at every level the constructors'
hints reach, and planned as the call builds them."""

import pytest

from pyct.binding.annotations import Builds, Fields, Items, NoOneClass, contradictions
from pyct.binding.builds import BuildError, object_forms, plan_call
from tests.unit.binding.hint_classes import Basket, Spot
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


def test_a_list_a_hint_builds_passes_its_items_by_position() -> None:
    args = {"s": [{"x": 1, "y": 2}, "a"]}

    plan = plan_call(args, (), None, HOME, SPOT)

    assert [(build.cls, build.place) for build in plan.builds] == [(Point, "s[0]"), (Spot, "s")]
    assert plan.builds[1].positional == [args["s"][0], "a"]
    assert plan.builds[1].keywords == {}


def test_a_list_under_a_hint_that_names_no_one_class_is_the_build_error() -> None:
    with pytest.raises(BuildError) as raised:
        plan_call({"s": [1]}, (), None, HOME, {"s": NoOneClass("the reason")})

    assert raised.value.place == "s"


ITEMS = {"items": Items(list, Builds(Point), fixed=True)}
BY = {"by": Items(dict, Builds(Point), fixed=True)}


def test_each_item_and_value_of_a_class_is_listed_by_its_place() -> None:
    args = {"items": [{"x": 1, "y": 2}, None, [3, 4]], "by": {"a": {"x": 5, "y": 6}, "b": 7}}

    found = object_forms(args, None, {**ITEMS, **BY}, HOME).found

    assert sorted(each.place for each in found) == ["by['a']", "items[0]", "items[2]"]
    assert all(each.check == Builds(Point) for each in found)
    assert args == {
        "items": [{"x": 1, "y": 2}, None, [3, 4]],
        "by": {"a": {"x": 5, "y": 6}, "b": 7},
    }


def test_a_list_of_lists_of_a_class_lists_the_inner_items() -> None:
    inner = Items(list, Builds(Point), fixed=True)
    args = {"rows": [[{"x": 1, "y": 2}]]}

    found = object_forms(args, None, {"rows": Items(list, inner, fixed=True)}, HOME).found

    assert [each.place for each in found] == ["rows[0][0]"]


def test_a_list_of_a_class_inside_a_hinted_and_a_named_object_is_listed() -> None:
    hinted = {"b": {"items": [{"x": 1, "y": 2}], "by": {}, "tags": []}}
    named = {"o": {"__class__": "Basket", "items": [{"x": 1, "y": 2}], "by": {}, "tags": []}}

    from_hint = object_forms(hinted, None, {"b": Builds(Basket)}, HOME).found
    from_name = object_forms(named, None, {}, HOME).found

    assert [each.place for each in from_hint] == ["b['items'][0]", "b"]
    assert [each.place for each in from_name] == ["o['items'][0]", "o"]


def test_a_named_object_inside_a_list_of_a_class_gives_its_siblings_their_hint() -> None:
    named = {"__class__": "tests.unit.binding.named_classes::Holder", "inner": 1}
    args = {"items": [named, {"x": 1, "y": 2}]}

    found = object_forms(args, None, ITEMS, HOME).found

    assert sorted((each.place, each.check) for each in found) == [
        ("items[0]", Builds(Point)),
        ("items[1]", Builds(Point)),
    ]


def test_the_plan_builds_each_item_into_a_copy_of_the_list() -> None:
    args = {"items": [{"x": 1, "y": 2}, None], "by": {"a": [3, 4]}}

    plan = plan_call(args, (), None, HOME, {**ITEMS, **BY})

    assert sorted(build.place for build in plan.builds) == ["by['a']", "items[0]"]
    items, by = plan.keywords["items"], plan.keywords["by"]
    assert items is not args["items"] and by is not args["by"]
    for build in plan.builds:
        build.into[build.slot] = build.cls(*build.positional, **build.keywords)
    assert isinstance(items[0], Point) and items[1] is None  # pyrefly: ignore[bad-index]
    assert isinstance(by["a"], Point)  # pyrefly: ignore[bad-index]
    assert args == {"items": [{"x": 1, "y": 2}, None], "by": {"a": [3, 4]}}


def test_an_empty_list_or_dict_of_a_class_plans_no_build() -> None:
    plan = plan_call({"items": [], "by": {}}, (), None, HOME, {**ITEMS, **BY})

    assert plan.builds == []
    assert plan.keywords == {"items": [], "by": {}}

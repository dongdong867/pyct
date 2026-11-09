"""The object forms of a seed, listed innermost first, and the plan of the call that builds them."""

import inspect
from collections.abc import Mapping

import pytest

from pyct.binding.builds import BuildError, SelfBuild, object_forms, plan_call
from pyct.binding.call import positional_only
from tests.unit.binding.named_classes import Holder, Pinned, Point

HOME = "tests.unit.binding.named_classes"
POINT = {"__class__": "Point", "x": 1, "y": 2}


def places(args: Mapping[str, object], self_name: str | None = None) -> list[str]:
    return [found.place for found in object_forms(args, self_name).found]


def test_forms_are_listed_innermost_first_and_siblings_in_seed_order() -> None:
    inner = {"__class__": "Holder", "inner": dict(POINT), "other": dict(POINT)}
    args = {"a": {"__class__": "Holder", "inner": inner}, "b": dict(POINT), "n": 3}

    assert places(args) == ["a['inner']['inner']", "a['inner']['other']", "a['inner']", "a", "b"]


def test_args_items_are_places_by_index() -> None:
    args = {"p": {"__class__": "Holder", "__args__": [dict(POINT)]}}

    assert places(args) == ["p['__args__'][0]", "p"]


def test_the_dict_under_self_is_no_form_but_its_values_are() -> None:
    args = {"self": {"__class__": "Shop", "owner": dict(POINT)}, "c": dict(POINT)}

    assert places(args, "self") == ["self['owner']", "c"]
    assert places(args) == ["self['owner']", "self", "c"]


def test_a_form_inside_a_plain_dict_or_list_stays_a_dict() -> None:
    assert places({"d": {"k": dict(POINT)}, "rows": [dict(POINT)]}) == []


def test_the_caller_s_seed_never_changes() -> None:
    items = [dict(POINT)]
    args = {"p": {"__class__": "Holder", "__args__": items}}

    forms = object_forms(args, None)

    assert forms.args == args
    assert forms.args["p"] is not args["p"]
    outer = forms.found[-1].form
    assert outer["__args__"] is not items
    assert forms.found[0].form is outer["__args__"][0]  # pyrefly: ignore[bad-index]


def test_the_plan_builds_inner_objects_into_the_outer_one_s_arguments() -> None:
    plan = plan_call({"h": {"__class__": "Holder", "inner": dict(POINT)}}, (), None, HOME)

    inner, outer = plan.builds
    assert (inner.cls, inner.place, inner.keywords) == (Point, "h['inner']", {"x": 1, "y": 2})
    assert (outer.cls, outer.place) == (Holder, "h")
    assert inner.into is outer.keywords and inner.slot == "inner"
    assert outer.into is plan.keywords and outer.slot == "h"


def test_args_items_go_first_then_positional_only_parameters_by_position() -> None:
    form = {"__class__": "Pinned", "b": 5, "a": 4}
    by_args = {"__class__": "Pinned", "__args__": [4], "b": 5}

    plan = plan_call({"p": form, "q": by_args}, (), None, HOME)

    first, second = plan.builds
    assert first.cls is second.cls is Pinned
    assert (first.positional, first.keywords) == ([4], {"b": 5})
    assert (second.positional, second.keywords) == ([4], {"b": 5})


def test_the_instance_a_method_runs_on_is_built_last_and_goes_first() -> None:
    def total(self: object, n: int, /) -> None: ...

    positional = positional_only(inspect.signature(total))
    self_build = SelfBuild(Holder, "self")
    args = {"self": {"inner": dict(POINT)}, "n": 3}

    plan = plan_call(args, positional, self_build, HOME)

    point, built = plan.builds
    assert (built.cls, built.place, built.into, built.slot) == (Holder, "self", plan.positional, 0)
    assert point.into is built.keywords and point.slot == "inner"
    assert plan.positional == [None, 3]


def test_a_value_under_self_other_than_a_dict_is_passed_as_given() -> None:
    given = Holder(1)

    plan = plan_call({"self": given}, (), SelfBuild(Holder, "self"), HOME)

    assert plan.builds == ()
    assert plan.keywords == {"self": given}


def test_a_class_that_does_not_load_is_a_build_error_at_its_place() -> None:
    with pytest.raises(BuildError) as raised:
        plan_call({"c": {"__class__": "Nothing"}}, (), None, HOME)

    assert (raised.value.place, raised.value.reason) == ("c", f"{HOME} has no class Nothing")


def test_the_first_object_that_cannot_be_built_is_the_innermost() -> None:
    args = {"c": {"__class__": "Nothing", "inner": {"__class__": "Missing"}}}

    with pytest.raises(BuildError) as raised:
        plan_call(args, (), None, HOME)

    assert raised.value.place == "c['inner']"


def test_args_that_is_not_a_list_is_a_build_error() -> None:
    with pytest.raises(BuildError) as raised:
        plan_call({"c": {"__class__": "Point", "__args__": "ann"}}, (), None, HOME)

    assert raised.value.reason == "'__args__' must be a list, got \"ann\""


def test_dropping_the_plan_lets_go_of_every_object() -> None:
    plan = plan_call({"h": {"__class__": "Holder", "inner": dict(POINT)}}, (), None, HOME)

    plan.drop()

    assert plan.keywords == {}
    assert all(not build.keywords and not build.positional for build in plan.builds)

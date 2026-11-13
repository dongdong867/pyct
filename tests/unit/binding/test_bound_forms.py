"""The call builds the object forms bind's walk copied as forms, and no other dict: a plain dict
that holds ``"__class__"`` once its escape is read stays a dict."""

from collections.abc import Mapping

import pytest

from pyct.binding.annotations import Builds, Check, Fields, Items
from pyct.binding.bind import bind, bind_call
from pyct.binding.builds import BuildError, CallPlan, SelfBuild, plan_call
from tests.unit.binding.hint_classes import Spot
from tests.unit.binding.named_classes import Holder, Point

HOME = "tests.unit.binding.hint_classes"
NAMED = "tests.unit.binding.named_classes"
POINT = {"__class__": f"{NAMED}::Point", "x": 1, "y": 2}
HOLDER = f"{NAMED}::Holder"
SPOT = {"s": Builds(Spot)}
ITEMS = {"items": Items(list, Builds(Point), fixed=True)}
BY = {"by": Items(dict, Builds(Point), fixed=True)}
SELF = SelfBuild(Holder, "self")


class Rows(list[object]):
    pass


def built(plan: CallPlan) -> list[tuple[type, str, list[object], dict[str, object]]]:
    """Each build of a plan: its class, its place, and what it is called with."""
    return [(each.cls, each.place, each.positional, each.keywords) for each in plan.builds]


@pytest.mark.parametrize(
    ("seed", "checks", "self_build"),
    [
        ({"c": POINT}, None, None),
        ({"rows": [{"c": POINT}, POINT]}, None, None),
        ({"d": {"ann": POINT, 2.5: POINT}}, None, None),
        ({"h": {"__class__": HOLDER, "inner": POINT}}, None, None),
        ({"p": {"__class__": HOLDER, "__args__": [POINT]}}, None, None),
        ({"self": {"inner": POINT}}, {"self": Fields({})}, SELF),
        ({"s": {"at": {"x": 1, "y": 2}, "label": "a"}}, SPOT, None),
        ({"s": [{"x": 1, "y": 2}, "a"]}, SPOT, None),
        ({"items": [{"x": 1, "y": 2}, None], "by": {"a": [3, 4]}}, {**ITEMS, **BY}, None),
        ({"t": (POINT,), "r": Rows([POINT])}, None, None),
    ],
    ids=[
        "parameter",
        "in lists",
        "in a dict",
        "keyword",
        "args item",
        "under self",
        "hinted dict",
        "hinted list",
        "list and dict of a class",
        "tuple and list subclass",
    ],
)
def test_the_walk_s_forms_plan_the_builds_the_seed_s_keys_and_hints_plan(
    seed: dict[str, object], checks: Mapping[str, Check] | None, self_build: SelfBuild | None
) -> None:
    today = plan_call(seed, (), self_build, HOME, checks)

    bound = plan_call(bind_call(seed, [], checks, HOME), (), self_build, HOME, checks)

    assert built(bound) == built(today)


def test_a_plain_dict_holding_an_object_and_an_escaped_key_stays_a_dict() -> None:
    seed = {"box": {"!__class__": 0, "b": POINT}}

    plan = plan_call(bind_call(seed, [], None, HOME), (), None, HOME)

    assert [(each.cls, each.place) for each in plan.builds] == [(Point, "box['b']")]
    box = plan.keywords["box"]
    assert isinstance(box, dict) and list(box) == ["__class__", "b"]
    with pytest.raises(BuildError):
        plan_call(bind(seed, [], None, HOME), (), None, HOME)


def test_a_dict_of_a_class_holding_an_escaped_key_builds_each_value() -> None:
    seed = {"by": {"!__class__": {"x": 1, "y": 2}, "k": {"x": 3, "y": 4}}}

    plan = plan_call(bind_call(seed, [], BY, HOME), (), None, HOME, BY)

    assert [(each.cls, each.place) for each in plan.builds] == [
        (Point, "by['__class__']"),
        (Point, "by['k']"),
    ]
    by = plan.keywords["by"]
    assert isinstance(by, dict) and list(by) == ["__class__", "k"]

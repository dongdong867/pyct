"""The call builds the object forms bind's walk copied as forms, and no other dict: a plain dict
that holds ``"__class__"`` once its escape is read stays a dict."""

from collections.abc import Mapping

import pytest

from pyct.binding.annotations import Builds, Check, Fields, Items
from pyct.binding.bind import bind_call
from pyct.binding.builds import SelfBuild, form_class, object_forms, plan_call
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


def by_the_seed(
    seed: dict[str, object], checks: Mapping[str, Check] | None, self_build: SelfBuild | None
) -> list[tuple[type, str]]:
    """The class and place of each object the seed's keys and hints make a form, and of the
    instance a method runs on, last."""
    name = None if self_build is None else self_build.name
    found = object_forms(seed, name, checks, HOME).found
    lasts = [] if self_build is None else [(self_build.cls, self_build.name)]
    return [*((form_class(each.form, each.check, HOME), each.place) for each in found), *lasts]


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
def test_the_walk_s_forms_plan_the_builds_the_seed_s_keys_and_hints_make(
    seed: dict[str, object], checks: Mapping[str, Check] | None, self_build: SelfBuild | None
) -> None:
    plan = plan_call(bind_call(seed, [], checks, HOME), (), self_build, HOME, checks)

    assert [(each.cls, each.place) for each in plan.builds] == by_the_seed(seed, checks, self_build)


def test_a_plain_dict_holding_an_object_and_an_escaped_key_stays_a_dict() -> None:
    seed = {"box": {"!__class__": 0, "b": POINT}}

    plan = plan_call(bind_call(seed, [], None, HOME), (), None, HOME)

    assert [(each.cls, each.place) for each in plan.builds] == [(Point, "box['b']")]
    box = plan.keywords["box"]
    assert isinstance(box, dict) and list(box) == ["__class__", "b"]


def test_a_dict_of_a_class_holding_an_escaped_key_builds_each_value() -> None:
    seed = {"by": {"!__class__": {"x": 1, "y": 2}, "k": {"x": 3, "y": 4}}}

    plan = plan_call(bind_call(seed, [], BY, HOME), (), None, HOME, BY)

    assert [(each.cls, each.place) for each in plan.builds] == [
        (Point, "by['__class__']"),
        (Point, "by['k']"),
    ]
    by = plan.keywords["by"]
    assert isinstance(by, dict) and list(by) == ["__class__", "k"]

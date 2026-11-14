"""A ``*args`` parameter's annotation checks and builds no seed key: a key with its name reaches
``**kwargs``, or does not fit. Each reader of the annotations agrees: the seed check, the check
on the object under ``self``, what the walk is given, and what each input builds."""

import inspect

from pyct.binding.annotations import Fields
from pyct.run.seed_checks import seed_refusals
from pyct.run.target import Target, argument_checks
from tests.unit.binding.plans import planned
from tests.unit.run.starred import HOME, Cart, target_for


class Gathers:
    def __init__(self, *items: list[str], **named: object) -> None:
        self.items, self.named = items, named

    def m(self) -> None:
        pass


class GathersCarts:
    def __init__(self, *items: Cart, **named: object) -> None:
        self.items, self.named = items, named


def spread(*items: int, **named: object) -> None:
    pass


def spread_carts(*items: Cart, **named: object) -> None:
    pass


def holds(g: GathersCarts) -> None:
    pass


GATHERS_M = Target(
    spec="m::Gathers.m",
    fn=Gathers.m,
    file="m.py",
    signature=inspect.signature(Gathers.m),
    self_class=Gathers,
    self_name="self",
    constructor=inspect.signature(Gathers),
)


def test_the_seed_check_takes_a_key_named_as_star_args_as_plain_python_does() -> None:
    spread(items="a")  # plain Python passes it to **named

    assert seed_refusals(target_for(spread), {"items": "a"}) == []


def test_the_walk_is_given_no_check_for_a_key_named_as_star_args() -> None:
    assert argument_checks(target_for(spread)) == {}


def test_the_check_under_self_takes_a_key_named_as_the_constructor_s_star_args() -> None:
    Gathers(items="a")  # plain Python passes it to **named

    assert seed_refusals(GATHERS_M, {"self": {"items": []}}) == []
    assert seed_refusals(GATHERS_M, {"self": {"items": "a"}}) == []


def test_the_walk_is_given_no_check_under_self_for_the_constructor_s_star_args() -> None:
    assert argument_checks(GATHERS_M) == {"self": Fields({})}


def test_a_class_hint_on_star_args_builds_no_object_under_a_key_of_that_name() -> None:
    args = {"items": {"owner": "a"}}

    plan = planned(args, (), None, HOME, argument_checks(target_for(spread_carts)))

    assert plan.builds == []
    assert plan.keywords == {"items": {"owner": "a"}}


def test_a_class_hint_on_a_built_object_s_star_args_builds_nothing_inside_it() -> None:
    args = {"g": {"items": {"owner": "a"}}}

    plan = planned(args, (), None, HOME, argument_checks(target_for(holds)))

    assert [(build.cls, build.place) for build in plan.builds] == [(GathersCarts, "g")]
    assert plan.builds[0].keywords == {"items": {"owner": "a"}}

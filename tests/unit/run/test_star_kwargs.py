"""A ``**kwargs`` parameter's annotation checks and builds no seed key: a key with its name is an
extra keyword, and the annotation describes each extra keyword's value, which pyct does not
check. Each reader of the annotations agrees: the seed check, the check on the object under
``self``, what the walk is given, and what each input builds."""

import inspect

from pyct.binding.annotations import Fields
from pyct.run.seed_checks import seed_refusals
from pyct.run.target import Target, argument_checks
from tests.unit.binding.plans import planned

HOME = __name__


class Cart:
    def __init__(self, owner: str) -> None:
        self.owner = owner


class K:
    def __init__(self, **named: int) -> None:
        self.named = named

    def m(self) -> None:
        pass


class KeepsCarts:
    def __init__(self, **named: Cart) -> None:
        self.named = named


def f(**named: int) -> None:
    pass


def g(**named: Cart) -> None:
    pass


def holds(k: KeepsCarts) -> None:
    pass


def target_for(fn: object) -> Target:
    assert callable(fn)
    return Target(spec="m::f", fn=fn, file="m.py", signature=inspect.signature(fn))


K_M = Target(
    spec="m::K.m",
    fn=K.m,
    file="m.py",
    signature=inspect.signature(K.m),
    self_class=K,
    self_name="self",
    constructor=inspect.signature(K),
)


def test_the_seed_check_takes_a_key_named_as_star_kwargs_as_plain_python_does() -> None:
    # plain Python runs it, passing {"named": "a"} to **named, whatever the annotation says
    f(named="a")  # pyrefly: ignore[bad-argument-type]

    assert seed_refusals(target_for(f), {"named": "a"}) == []


def test_the_walk_is_given_no_check_for_a_key_named_as_star_kwargs() -> None:
    assert argument_checks(target_for(f)) == {}


def test_the_check_under_self_takes_a_key_named_as_the_constructor_s_star_kwargs() -> None:
    # plain Python runs it, passing {"named": "a"} to **named, whatever the annotation says
    K(named="a")  # pyrefly: ignore[bad-argument-type]

    assert seed_refusals(K_M, {"self": {"named": "a"}}) == []


def test_the_walk_is_given_no_check_under_self_for_the_constructor_s_star_kwargs() -> None:
    assert argument_checks(K_M) == {"self": Fields({})}


def test_a_class_hint_on_star_kwargs_builds_no_object_under_a_key_of_that_name() -> None:
    args = {"named": {"owner": "a"}}

    plan = planned(args, (), None, HOME, argument_checks(target_for(g)))

    assert plan.builds == []
    assert plan.keywords == {"named": {"owner": "a"}}


def test_a_class_hint_on_a_built_object_s_star_kwargs_builds_nothing_inside_it() -> None:
    args = {"k": {"named": {"owner": "a"}}}

    plan = planned(args, (), None, HOME, argument_checks(target_for(holds)))

    assert [(build.cls, build.place) for build in plan.builds] == [(KeepsCarts, "k")]
    assert plan.builds[0].keywords == {"named": {"owner": "a"}}

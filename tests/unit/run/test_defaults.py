"""A constructor parameter the seed leaves out under ``self``, filled with its simple default."""

import enum
import inspect

from pyct.run.defaults import with_defaults
from pyct.run.isolation import Isolation
from pyct.run.run import run
from pyct.run.target import Target
from pyct.run.target import _constructor as constructor_of


class Size(enum.IntEnum):
    SMALL = 1


class Member:
    """A constructor with a default of each simple type."""

    def __init__(
        self, name: str, vip: bool = False, rank: int = 2, rate: float = 0.5, note: str = ""
    ) -> None:
        self.name = name
        self.vip = vip

    def price(self) -> int:
        if self.vip:
            return 5
        return 10


class Gathering:
    """A constructor whose other defaults, and gathering parameters, Python fills itself."""

    def __init__(
        self,
        name: str,
        tags: list[str] | None = None,
        size: Size = Size.SMALL,
        *extra: object,
        level: int = 3,
        **more: object,
    ) -> None:
        self.name = name

    def show(self) -> str:
        return self.name


class Unread:
    """A class whose signature Python cannot read."""

    __signature__ = 5

    def __init__(self, n: int, flag: bool = False) -> None:
        self.n = n

    def check(self) -> str:
        if self.n > 0:
            return "positive"
        return "other"


def target_of(cls: type, method: object, constructor: inspect.Signature | None) -> Target:
    """A target for ``method`` that builds an instance of ``cls`` under ``self``."""
    return Target(
        spec=f"{__name__}::{cls.__name__}.{getattr(method, '__name__', '')}",
        fn=method,  # pyrefly: ignore[bad-argument-type]
        file=__file__,
        signature=inspect.signature(method),  # pyrefly: ignore[bad-argument-type]
        self_class=cls,
        self_name="self",
        constructor=constructor,
    )


MEMBER = target_of(Member, Member.price, inspect.signature(Member))


def test_a_left_out_int_float_str_or_bool_default_is_filled_after_the_given_keys() -> None:
    seed: dict[str, object] = {"self": {"name": "ann", "rank": 9}}

    filled = with_defaults(MEMBER, seed)

    assert filled == {"self": {"name": "ann", "rank": 9, "vip": False, "rate": 0.5, "note": ""}}
    fields = filled["self"]
    assert isinstance(fields, dict)
    assert list(fields) == ["name", "rank", "vip", "rate", "note"]
    assert seed == {"self": {"name": "ann", "rank": 9}}


def test_only_a_simple_default_is_filled_a_keyword_only_one_too() -> None:
    gathering = target_of(Gathering, Gathering.show, inspect.signature(Gathering))

    assert with_defaults(gathering, {"self": {"name": "ann"}}) == {
        "self": {"name": "ann", "level": 3}
    }


def test_a_seed_whose_self_is_not_a_dict_is_left_as_it_came() -> None:
    given = Member("ann")

    assert with_defaults(MEMBER, {"self": given}) == {"self": given}
    assert with_defaults(MEMBER, {"self": 5}) == {"self": 5}


def test_a_target_that_builds_no_self_fills_nothing() -> None:
    plain = Target(
        spec=f"{__name__}::Member", fn=Member, file=__file__, signature=inspect.signature(Member)
    )

    assert with_defaults(plain, {"name": "ann"}) == {"name": "ann"}


def test_a_class_whose_signature_python_cannot_read_has_no_constructor() -> None:
    assert constructor_of(Unread) is None


def test_a_class_whose_signature_python_cannot_read_is_built_with_no_filled_default() -> None:
    target = target_of(Unread, Unread.check, None)

    result = run(target, {"self": {"n": 1}}, isolation=Isolation.IN_PROCESS)

    first = result.records[0]
    assert first.args == {"self": {"n": 1}}
    assert first.failure is None
    assert [fork.expression for fork in first.forks] == [[">", ["[]", "self", "'n'"], 0]]


def test_each_of_several_seeds_takes_its_left_out_defaults_and_keeps_its_keys() -> None:
    seeds = [{"self": {"name": "ann"}}, {"self": {"name": "bob", "vip": True}}]

    result = run(MEMBER, seeds, isolation=Isolation.IN_PROCESS)

    simple = {"rank": 2, "rate": 0.5, "note": ""}
    assert [record.args for record in result.records[:2]] == [
        {"self": {"name": "ann", "vip": False, **simple}},
        {"self": {"name": "bob", "vip": True, **simple}},
    ]
    vip = ["[]", "self", "'vip'"]
    assert [[fork.expression for fork in record.forks] for record in result.records[:2]] == [
        [vip],
        [vip],
    ]

"""A constructor parameter the seed leaves out under ``self``, filled with its simple default."""

import enum
import inspect

from pyct.binding.classes import constructor as constructor_of
from pyct.run.defaults import with_defaults
from pyct.run.isolation import Isolation
from pyct.run.run import run
from pyct.run.setup import Setup
from pyct.run.target import Target


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

    result = run(target, {"self": {"n": 1}}, setup=Setup(isolation=Isolation.IN_PROCESS))

    first = result.records[0]
    assert first.args == {"self": {"n": 1}}
    assert first.failure is None
    assert [fork.expression for fork in first.forks] == [[">", ["[]", "self", "'n'"], 0]]


def test_each_of_several_seeds_takes_its_left_out_defaults_and_keeps_its_keys() -> None:
    seeds = [{"self": {"name": "ann"}}, {"self": {"name": "bob", "vip": True}}]

    result = run(MEMBER, seeds, setup=Setup(isolation=Isolation.IN_PROCESS))

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


class Account:
    """A constructor with simple defaults, a positional-only one among them, for an object a
    seed names with ``"__class__"``."""

    def __init__(self, owner: str, /, limit: int = 10, *, plan: str = "free") -> None:
        self.owner = owner


class Wrapper:
    def __init__(self, inner: object, size: int = 1) -> None:
        self.inner = inner


def takes(a: object, b: object = None) -> None:
    """A target whose arguments are objects the seed names, its classes read here."""


TAKES = Target(
    spec=f"{__name__}::takes", fn=takes, file=__file__, signature=inspect.signature(takes)
)


def test_an_object_form_s_simple_defaults_are_filled_at_any_depth() -> None:
    inner = {"__class__": "Account", "owner": "ann"}
    seed: dict[str, object] = {"a": {"__class__": "Wrapper", "inner": inner}}

    filled = with_defaults(TAKES, seed)

    assert filled == {
        "a": {
            "__class__": "Wrapper",
            "inner": {"__class__": "Account", "owner": "ann", "limit": 10, "plan": "free"},
            "size": 1,
        }
    }
    assert seed == {
        "a": {"__class__": "Wrapper", "inner": {"__class__": "Account", "owner": "ann"}}
    }


def test_an_object_inside_a_list_or_dict_takes_its_defaults() -> None:
    account = {"__class__": "Account", "owner": "ann"}
    seed: dict[str, object] = {"a": [{"k": dict(account)}], "b": {"x": dict(account)}}

    filled = with_defaults(TAKES, seed)

    with_both = {**account, "limit": 10, "plan": "free"}
    assert filled == {"a": [{"k": with_both}], "b": {"x": with_both}}
    assert seed == {"a": [{"k": account}], "b": {"x": account}}


def test_a_parameter_args_fills_by_position_is_not_filled() -> None:
    seed: dict[str, object] = {"a": {"__class__": "Account", "__args__": ["ann", 3]}}

    assert with_defaults(TAKES, seed) == {
        "a": {"__class__": "Account", "__args__": ["ann", 3], "plan": "free"}
    }


def test_an_object_under_self_s_fields_takes_its_defaults() -> None:
    seed: dict[str, object] = {
        "self": {"name": "ann", "vip": True, "rank": {"__class__": "Wrapper", "inner": 1}}
    }

    filled = with_defaults(MEMBER, seed)

    fields = filled["self"]
    assert isinstance(fields, dict)
    assert fields["rank"] == {"__class__": "Wrapper", "inner": 1, "size": 1}


def test_a_class_python_cannot_read_or_load_gets_none_and_the_objects_inside_still_do() -> None:
    account = {"__class__": "Account", "owner": "ann"}
    filled_account = {**account, "limit": 10, "plan": "free"}
    unread = {"__class__": "Unread", "n": 1, "flag": account}
    nowhere = {"__class__": "Nowhere", "x": dict(account)}

    filled = with_defaults(TAKES, {"a": unread, "b": nowhere})

    assert filled == {
        "a": {"__class__": "Unread", "n": 1, "flag": filled_account},
        "b": {"__class__": "Nowhere", "x": filled_account},
    }


class Holding:
    """A class a seed names, whose constructor's hint builds the object inside."""

    def __init__(self, member: Member) -> None:
        self.member = member


def hinted(a: Member, b: object = None) -> None:
    """A target whose first parameter's hint builds a Member."""


HINTED = Target(
    spec=f"{__name__}::hinted", fn=hinted, file=__file__, signature=inspect.signature(hinted)
)
MEMBER_DEFAULTS = {"vip": False, "rank": 2, "rate": 0.5, "note": ""}


def test_an_object_a_hint_builds_takes_its_defaults() -> None:
    seed: dict[str, object] = {"a": {"name": "ann"}}

    assert with_defaults(HINTED, seed) == {"a": {"name": "ann", **MEMBER_DEFAULTS}}
    assert seed == {"a": {"name": "ann"}}


def test_a_list_a_hint_builds_fills_no_default() -> None:
    assert with_defaults(HINTED, {"a": ["ann"]}) == {"a": ["ann"]}


def test_an_object_a_hint_builds_inside_a_named_object_takes_its_defaults() -> None:
    seed: dict[str, object] = {"a": None, "b": {"__class__": "Holding", "member": {"name": "ann"}}}

    filled = with_defaults(HINTED, seed)

    assert filled["b"] == {"__class__": "Holding", "member": {"name": "ann", **MEMBER_DEFAULTS}}


class Line:
    """An item with a simple default, under a list and a dict hint."""

    def __init__(self, sku: str, qty: int = 1) -> None:
        self.sku = sku


class Cart:
    def __init__(self, lines: list[Line], note: str = "") -> None:
        self.lines = lines


def holds(items: list[Line], by: dict[str, Line]) -> None:
    """A target whose list and dict hints build each item and value."""


HOLDS = Target(
    spec=f"{__name__}::holds", fn=holds, file=__file__, signature=inspect.signature(holds)
)


def test_each_item_and_value_a_list_or_dict_hint_builds_takes_its_defaults() -> None:
    seed: dict[str, object] = {"items": [{"sku": "a"}, None], "by": {"k": {"sku": "b"}}}

    filled = with_defaults(HOLDS, seed)

    assert filled == {
        "items": [{"sku": "a", "qty": 1}, None],
        "by": {"k": {"sku": "b", "qty": 1}},
    }
    assert seed == {"items": [{"sku": "a"}, None], "by": {"k": {"sku": "b"}}}


def test_a_list_hint_s_items_under_a_named_object_take_their_defaults() -> None:
    seed: dict[str, object] = {"a": {"__class__": "Cart", "lines": [{"sku": "a"}]}}

    filled = with_defaults(TAKES, seed)

    assert filled == {"a": {"__class__": "Cart", "lines": [{"sku": "a", "qty": 1}], "note": ""}}

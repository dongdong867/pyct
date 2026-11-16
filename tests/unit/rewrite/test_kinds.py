"""Each parameter of an input is an object, holds one, or is plain, decided from its value, what its
hint asks and the method's ``self`` parameter, with no hook of the value's class or metaclass
run."""

from collections.abc import Mapping

import pytest

from pyct.binding.annotations import Builds, Check, Fields, Items, NoOneClass
from pyct.binding.bind import Seed
from pyct.rewrite.kinds import Kind, Kinds, kind_of
from tests.unit.rewrite.orders import Order

ORDER = Builds(Order)
LIST_OF_ORDERS = Items(list, ORDER, fixed=True)
DICT_OF_ORDERS = Items(dict, ORDER, fixed=True)
FORM = {"__class__": "m::Order", "code": "0"}


def guarded_instance() -> object:
    """An instance whose class's metaclass raises in ``__hash__``, ``__eq__`` and
    ``__getattribute__``, made here so no collection reads the class."""

    class Raising(type):
        def __hash__(cls) -> int:
            raise AssertionError("the metaclass's __hash__ ran")

        def __eq__(cls, other: object) -> bool:
            raise AssertionError("the metaclass's __eq__ ran")

        def __getattribute__(cls, name: str) -> object:
            raise AssertionError(f"the metaclass's __getattribute__ ran for {name}")

    class Guarded(metaclass=Raising):
        pass

    return Guarded()


@pytest.mark.parametrize(
    ("value", "check"),
    [
        (FORM, None),
        ({"code": "0"}, ORDER),
        (["0"], ORDER),
        ({"code": "0"}, NoOneClass("names two classes", (Order, Order))),
        (Order("0"), None),
        ({1, 2}, None),
        (b"x", None),
    ],
)
def test_a_value_the_input_builds_or_of_any_other_type_is_an_object(
    value: object, check: Check | None
) -> None:
    assert kind_of(value, check) is Kind.OBJECT


@pytest.mark.parametrize(
    ("value", "check"),
    [
        ([{"code": "0"}], LIST_OF_ORDERS),
        ({"a": {"code": "0"}}, DICT_OF_ORDERS),
        ([[{"code": "0"}]], Items(list, LIST_OF_ORDERS, fixed=True)),
        ([1, {"k": FORM}], None),
        ({"k": [Order("0")]}, None),
        ({Order("0"): 1}, None),
        ((1, ("x", Order("0"))), None),
    ],
)
def test_a_list_tuple_or_dict_with_an_object_at_any_depth_holds_one(
    value: object, check: Check | None
) -> None:
    assert kind_of(value, check) is Kind.HOLDS_OBJECT


@pytest.mark.parametrize(
    ("value", "check"),
    [
        ({"k": [1, (2.5, "x", None, True)], "j": {"__args__": [1]}}, None),
        ([{"code": "0"}], Items(list, int)),
        ({"1": {"code": "0"}}, Items(dict, None, keys=int)),
        ({"code": "0"}, LIST_OF_ORDERS),
        (None, ORDER),
        ("0", ORDER),
    ],
)
def test_a_value_no_hint_builds_and_that_holds_no_object_is_plain(
    value: object, check: Check | None
) -> None:
    assert kind_of(value, check) is Kind.PLAIN


# llm-rewrite-hint-built-object-runs-no-metaclass-code: deciding the kinds runs no metaclass code
def test_an_instance_whose_metaclass_hooks_raise_is_told_apart_with_none_run() -> None:
    guarded = guarded_instance()

    assert kind_of(guarded) is Kind.OBJECT
    assert kind_of((1, ["x", guarded])) is Kind.HOLDS_OBJECT


def test_a_list_that_holds_itself_is_read_once() -> None:
    cycle: list[object] = [1]
    cycle.append(cycle)

    assert kind_of(cycle) is Kind.PLAIN


def test_the_dict_a_method_s_self_is_built_from_is_an_object() -> None:
    kinds = Kinds({"self": Fields({"code": str})}, "self")

    assert kinds.of("self", {"code": "0"}) is Kind.OBJECT
    assert kinds.of("s", {"code": "0"}) is Kind.PLAIN


def test_self_given_as_no_dict_is_read_by_its_value() -> None:
    kinds = Kinds({}, "self")

    assert kinds.of("self", "0") is Kind.PLAIN
    assert kinds.of("self", Order("0")) is Kind.OBJECT


def test_each_name_s_kind_reads_its_own_hint() -> None:
    kinds = Kinds({"order": ORDER})

    assert kinds.of("order", {"code": "0"}) is Kind.OBJECT
    assert kinds.of("other", {"code": "0"}) is Kind.PLAIN


def test_a_seed_s_kinds_read_the_hints_it_was_made_with() -> None:
    hinted = Seed.of({"order": {"code": "0"}, "s": "0"}, {"order": ORDER})
    unhinted = Seed.of({"order": {"code": "0"}, "s": "0"})

    assert Kinds.of_seed(hinted).fit(hinted.args, ("s",))
    assert not Kinds.of_seed(hinted).fit(hinted.args, ("order", "s"))
    assert Kinds.of_seed(unhinted).fit(unhinted.args, ("order", "s"))


def test_a_name_the_input_lacks_is_not_plain() -> None:
    args: Mapping[str, object] = {"s": "0"}

    assert not Kinds().fit(args, ("s", "t"))

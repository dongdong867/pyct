import inspect

import pytest

from pyct.config.command_line import UsageError
from pyct.run.seed_checks import check_seed, parse_seed, seed_refusals
from pyct.run.target import Target
from tests.nesting import nested_text, seed_limits


def classify(x: int) -> str:
    return "positive" if x > 0 else "other"


def target_for(fn: object) -> Target:
    """A Target around ``fn``, as the seed checks read it."""
    assert callable(fn)
    return Target(spec="m::f", fn=fn, file="m.py", signature=inspect.signature(fn))


CLASSIFY = target_for(classify)


@pytest.mark.parametrize("text", ["[1]", "1", '"x"', "null", "not json", ""])
def test_parse_seed_refuses_anything_but_an_object(text: str) -> None:
    with pytest.raises(UsageError, match="JSON object"):
        parse_seed(text)


def test_parse_seed_returns_the_object() -> None:
    assert parse_seed('{"x": 1, "s": "a"}') == {"x": 1, "s": "a"}


def test_check_seed_refuses_an_unexpected_key() -> None:
    with pytest.raises(UsageError, match="y"):
        check_seed(CLASSIFY, {"y": 1})


def test_check_seed_refuses_a_missing_key() -> None:
    with pytest.raises(UsageError, match="x"):
        check_seed(CLASSIFY, {})


def check(value: str, /, strict: bool = False) -> str:
    return value if strict else ""


def test_check_seed_takes_a_positional_only_parameter_by_name() -> None:
    check_seed(target_for(check), {"value": "x", "strict": True})


def test_check_seed_refuses_a_missing_positional_only_parameter() -> None:
    with pytest.raises(UsageError, match="value"):
        check_seed(target_for(check), {"strict": True})


def test_check_seed_accepts_a_fitting_seed() -> None:
    check_seed(CLASSIFY, {"x": 1})


def test_seed_refusals_check_the_types_once_the_names_fit() -> None:
    assert seed_refusals(CLASSIFY, {"x": "a"}) == ['x must be an int, got "a"']


def test_parse_seed_takes_a_seed_nested_thousands_deep() -> None:
    assert parse_seed(nested_text(2000))


def test_parse_seed_refuses_a_seed_too_deep_for_python_to_read() -> None:
    _, read = seed_limits()

    with pytest.raises(UsageError, match="too deep for Python to read"):
        parse_seed(nested_text(read))


def test_parse_seed_refuses_a_seed_too_deep_to_write() -> None:
    write, read = seed_limits()
    if write >= read:
        pytest.skip("this Python refuses to read a seed before it is too deep to write")

    with pytest.raises(UsageError, match="too deep for pyct to write"):
        parse_seed(nested_text(write))


class Cart:
    def __init__(self, owner: str) -> None:
        self.owner = owner

    def total(self, discount: int) -> int:
        return discount


# the method's signature with an annotation on self, which the check under self replaces
_TOTAL = inspect.signature(Cart.total)
_SELF = _TOTAL.parameters["self"].replace(annotation=str)
CART = Target(
    spec="m::Cart.total",
    fn=Cart.total,
    file="m.py",
    signature=_TOTAL.replace(parameters=[_SELF, _TOTAL.parameters["discount"]]),
    self_class=Cart,
    self_name="self",
    constructor=inspect.signature(Cart),
)


def test_seed_refusals_give_the_method_s_fit_alone_when_it_fails() -> None:
    refusals = seed_refusals(CART, {"self": 5, "count": "5"})

    assert len(refusals) == 1
    assert refusals[0].startswith("args (self, count) do not fit (self, discount): ")


def test_seed_refusals_give_the_lines_under_self_before_the_other_parameters() -> None:
    assert seed_refusals(CART, {"discount": "5", "self": {"owner": 5}}) == [
        "self['owner'] must be a str, got 5",
        'discount must be an int, got "5"',
    ]


def test_seed_refusals_check_self_against_the_constructor_and_not_its_own_annotation() -> None:
    assert seed_refusals(CART, {"self": 5, "discount": 1}) == [
        "self must be a JSON object of Cart's constructor arguments, got 5"
    ]


def test_seed_refusals_pass_a_seed_that_fits() -> None:
    assert seed_refusals(CART, {"self": {"owner": "ann"}, "discount": 1}) == []


def test_check_seed_raises_every_refusal_as_one_line_each() -> None:
    with pytest.raises(UsageError) as raised:
        check_seed(CART, {"self": {"owner": 5, "__calls__": []}, "discount": 1.5})

    assert str(raised.value).splitlines() == [
        "self cannot hold '__calls__': pyct reserves keys that start and end with __",
        "self['owner'] must be a str, got 5",
        "discount must be an int, got 1.5",
    ]


def test_seed_refusals_check_nothing_under_a_self_the_seed_leaves_to_its_default() -> None:
    discount = _TOTAL.parameters["discount"].replace(default=0)
    signature = _TOTAL.replace(parameters=[_SELF.replace(default=None), discount])
    target = Target(
        spec="m::Cart.total",
        fn=Cart.total,
        file="m.py",
        signature=signature,
        self_class=Cart,
        self_name="self",
        constructor=inspect.signature(Cart),
    )

    assert seed_refusals(target, {"discount": "1"}) == ['discount must be an int, got "1"']


class Customer:
    def __init__(self, name, age, vip=False):  # noqa: ANN001
        self.name, self.age, self.vip = name, age, vip


class Guest:
    def __init__(self, name: str, age: int, tags: list[str]) -> None:
        self.name, self.age, self.tags = name, age, tags


def takes_an_int(c: int) -> None:
    pass


def takes_a_dict(c: dict[str, str]) -> None:
    pass


def takes_anything(c) -> None:  # noqa: ANN001
    pass


@pytest.mark.parametrize("fn", [takes_an_int, takes_a_dict], ids=["int", "dict"])
def test_a_parameter_s_annotation_gives_no_line_for_an_object_the_seed_names(fn: object) -> None:
    seed = {"c": {"__class__": "Customer", "name": "ann", "age": 30}}

    assert seed_refusals(target_for(fn), seed) == []


def test_the_objects_inside_one_whose_class_does_not_load_are_still_checked() -> None:
    inner = {"__class__": "Customer", "name": "ann", "age": 30, "__calls__": []}
    seed = {"c": {"__class__": "Nowhere", "customer": inner}}

    lines = seed_refusals(target_for(takes_anything), seed)

    assert lines == [
        f"c['__class__']: {__name__} has no class Nowhere",
        "c['customer'] cannot hold '__calls__': pyct reserves keys that start and end with __",
    ]


def test_args_that_are_not_a_list_skip_the_fit_and_keep_the_other_lines() -> None:
    guest = {"__class__": "Guest", "__args__": "ann", "age": "30", "__calls__": []}

    lines = seed_refusals(target_for(takes_anything), {"c": guest})

    assert lines == [
        "c['__args__'] must be a list, got \"ann\"",
        "c cannot hold '__calls__': pyct reserves keys that start and end with __",
        "c['age'] must be an int, got \"30\"",
    ]

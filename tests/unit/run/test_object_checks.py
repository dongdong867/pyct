import inspect

from pyct.binding.builds import object_forms
from pyct.run.object_checks import ObjectCheck, form_lines

RESERVED = "pyct reserves keys that start and end with __"


class Cart:
    def __init__(self, owner: str, discount: int = 0) -> None:
        self.owner = owner
        self.discount = discount


class Point:
    def __init__(self, x: int, y: int, /, name: str = "") -> None:
        self.x, self.y, self.name = x, y, name


class Empty:
    pass


def check_for(cls: type) -> ObjectCheck:
    return ObjectCheck.of(cls, inspect.signature(cls))


def reason(cls: type, *args: object, **kwargs: object) -> str:
    """What plain Python says binding these arguments to ``cls``'s signature, in this run."""
    try:
        inspect.signature(cls).bind(*args, **kwargs)
    except TypeError as error:
        return str(error)
    raise AssertionError("the arguments bind")


def test_lines_are_none_for_an_object_that_fits() -> None:
    assert check_for(Cart).lines("self", {"owner": "ann"}) == []


def test_lines_refuse_a_value_that_is_not_a_json_object() -> None:
    check = check_for(Cart)

    assert check.lines("self", 5) == [
        "self must be a JSON object of Cart's constructor arguments, got 5"
    ]
    assert check.lines("o['customer']", ["ann"]) == [
        "o['customer'] must be a JSON object of Cart's constructor arguments, got [\"ann\"]"
    ]


def test_lines_name_a_nested_class_by_its_qualified_name() -> None:
    class Inner:
        pass

    lines = ObjectCheck.of(Inner, inspect.signature(Inner)).lines("self", None)

    assert lines == [
        "self must be a JSON object of"
        " test_lines_name_a_nested_class_by_its_qualified_name.<locals>.Inner's"
        " constructor arguments, got null"
    ]


def test_lines_refuse_each_reserved_key_in_the_seed_s_order() -> None:
    lines = check_for(Cart).lines("self", {"__calls__": [], "owner": "ann", "__class__": "Cart"})

    assert lines == [
        f"self cannot hold '__calls__': {RESERVED}",
        f"self cannot hold '__class__': {RESERVED}",
    ]


def test_lines_pass_an_allowed_reserved_key() -> None:
    lines = check_for(Cart).lines("c", {"__class__": "Cart", "owner": "ann"}, allowed={"__class__"})

    assert lines == []


def test_lines_refuse_keys_that_do_not_fit_the_constructor() -> None:
    lines = check_for(Cart).lines("rows[0]['c']", {"colour": "red"})

    assert lines == [
        f"rows[0]['c'] (colour) does not fit Cart(owner, discount): {reason(Cart, colour='red')}"
    ]


def test_lines_write_nothing_for_the_keys_of_an_empty_object_that_does_not_fit() -> None:
    assert check_for(Cart).lines("self", {}) == [
        f"self (nothing) does not fit Cart(owner, discount): {reason(Cart)}"
    ]


def test_lines_write_a_constructor_with_no_parameters_with_empty_brackets() -> None:
    assert check_for(Empty).lines("self", {"n": 1}) == [
        f"self (n) does not fit Empty(): {reason(Empty, n=1)}"
    ]


def test_lines_name_each_value_that_contradicts_the_constructor_under_the_place() -> None:
    lines = check_for(Cart).lines("o['customer']", {"owner": 5, "discount": "5"})

    assert lines == [
        "o['customer']['owner'] must be a str, got 5",
        "o['customer']['discount'] must be an int, got \"5\"",
    ]


def test_lines_give_every_line_of_one_object_at_once() -> None:
    lines = check_for(Cart).lines("self", {"owner": 5, "colour": "red", "__calls__": []})

    fit = reason(Cart, owner=5, colour="red")
    assert lines == [
        f"self cannot hold '__calls__': {RESERVED}",
        f"self (owner, colour) does not fit Cart(owner, discount): {fit}",
        "self['owner'] must be a str, got 5",
    ]


def test_lines_bind_a_positional_only_parameter_by_position() -> None:
    assert check_for(Point).lines("p", {"x": 1, "y": 2}) == []


def test_lines_bind_positional_items_first() -> None:
    check = check_for(Point)

    lines = check.lines(
        "p", {"__args__": [1, 2], "name": "a"}, allowed={"__args__"}, positional=(1, 2)
    )

    assert lines == []


def test_lines_bind_the_positional_only_parameters_the_items_leave_by_position() -> None:
    seed = {"__args__": [1], "y": 2}

    assert check_for(Point).lines("p", seed, allowed={"__args__"}, positional=(1,)) == []


def test_lines_refuse_a_key_for_a_positional_only_parameter_an_item_fills() -> None:
    seed = {"__args__": [1], "x": 9}

    lines = check_for(Point).lines("p", seed, allowed={"__args__"}, positional=(1,))

    assert lines == [f"p (__args__, x) does not fit Point(x, y, name): {reason(Point, 1, x=9)}"]


class Spread:
    def __init__(self, *items: int, **named: object) -> None:
        self.items, self.named = items, named


def test_lines_check_no_key_against_the_annotation_of_star_args() -> None:
    # a key named as *args reaches the constructor through **named, so the annotation on *items
    # does not apply to it
    assert check_for(Spread).lines("self", {"items": ["a"]}) == []


class Items:
    def __init__(self, *items: int) -> None:
        self.items = items


def test_lines_give_the_fit_alone_for_a_key_named_as_star_args_with_no_star_star() -> None:
    fit = reason(Items, items="a")

    assert check_for(Items).lines("self", {"items": "a"}) == [
        f"self (items) does not fit Items(items): {fit}"
    ]


def test_lines_list_the_positional_items_when_they_do_not_fit() -> None:
    check = check_for(Point)
    seed = {"__class__": "Point", "__args__": [1, 2, 3], "name": "a"}

    lines = check.lines("c", seed, allowed={"__class__", "__args__"}, positional=(1, 2, 3))

    fit = reason(Point, 1, 2, 3, name="a")
    # the third item fills name by position, so it is checked against name's annotation too
    assert lines == [
        f"c (__args__, name) does not fit Point(x, y, name): {fit}",
        "c['__args__'][2] must be a str, got 3",
    ]


def test_lines_check_only_the_shape_and_reserved_keys_with_no_signature() -> None:
    check = ObjectCheck.of(Cart, None)

    assert check.lines("self", {"colour": 5}) == []
    assert check.lines("self", 5) == [
        "self must be a JSON object of Cart's constructor arguments, got 5"
    ]
    assert check.lines("self", {"__calls__": []}) == [f"self cannot hold '__calls__': {RESERVED}"]


def test_lines_give_no_type_line_for_an_object_each_input_builds() -> None:
    owner = {"__class__": "Customer", "name": "ann"}

    lines = check_for(Cart).lines("self", {"owner": owner}, built=frozenset({id(owner)}))

    assert lines == []


def test_lines_check_each_positional_item_against_the_parameter_it_fills() -> None:
    seed = {"__args__": ["1"], "y": "2"}

    lines = check_for(Point).lines("p", seed, allowed={"__args__"}, positional=["1"])

    assert lines == [
        "p['__args__'][0] must be an int, got \"1\"",
        "p['y'] must be an int, got \"2\"",
    ]


def test_lines_check_no_item_past_the_parameters_that_take_a_position() -> None:
    seed = {"__args__": ["a", "b"]}

    assert check_for(Spread).lines("t", seed, allowed={"__args__"}, positional=["a", "b"]) == []


def test_lines_give_no_type_line_for_an_item_each_input_builds() -> None:
    item = {"__class__": "Customer", "name": "ann"}
    seed = {"__args__": [item, 2]}

    lines = check_for(Point).lines("p", seed, {"__args__"}, [item, 2], frozenset({id(item)}))

    assert lines == []


def test_lines_with_unknown_positions_check_no_fit_and_no_item() -> None:
    seed = {"__args__": "a", "name": 5}

    lines = check_for(Point).lines("p", seed, allowed={"__args__"}, positional=None)

    assert lines == ["p['name'] must be a str, got 5"]


def form_lines_of(seed: dict[str, object]) -> list[str]:
    """Every object's lines for ``seed``, its bare class names read in this module."""
    forms = object_forms(seed, None)
    built = frozenset(id(found.form) for found in forms.found)
    return [line for found in forms.outer_first() for line in form_lines(found, __name__, built)]


def test_form_lines_refuse_a_reserved_key_of_a_class_python_cannot_read() -> None:
    date = {"__class__": "datetime::date", "year": 2024, "month": 1, "day": 1, "__calls__": []}

    assert form_lines_of({"d": date}) == [f"d cannot hold '__calls__': {RESERVED}"]


def test_form_lines_give_the_fit_and_the_values_of_one_object_together() -> None:
    lines = form_lines_of({"c": {"__class__": "Cart", "owner": 5, "colour": "red"}})

    fit = reason(Cart, owner=5, colour="red")
    assert lines == [
        f"c (owner, colour) does not fit Cart(owner, discount): {fit}",
        "c['owner'] must be a str, got 5",
    ]


def test_form_lines_check_an_object_inside_an_object_by_its_own_class() -> None:
    inner = {"__class__": "Cart", "owner": 5}

    assert form_lines_of({"p": {"__class__": "Point", "__args__": [inner, 2]}}) == [
        "p['__args__'][0]['owner'] must be a str, got 5"
    ]

import inspect

from pyct.run.object_checks import ObjectCheck

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
    assert lines == [f"c (__args__, name) does not fit Point(x, y, name): {fit}"]


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

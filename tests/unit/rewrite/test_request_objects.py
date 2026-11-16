"""A request writes an object an input builds as its class and the arguments it is built from, as
JSON with no ``"__class__"``, and as its class alone when those arguments are no plain data, when
JSON cannot hold them or when they run too long; it writes them without running the target's
code."""

import pytest

from pyct.binding.annotations import Builds, NoOneClass
from pyct.binding.bind import Seed
from pyct.rewrite.kinds import Kinds
from pyct.rewrite.request import VALUE_SIZE, args_text
from tests.unit.rewrite.orders import Order


class Code(str):
    """A str whose ``__str__`` and ``__repr__`` raise, so writing it would run its code."""

    def __str__(self) -> str:
        raise RuntimeError("str ran")

    def __repr__(self) -> str:
        raise RuntimeError("repr ran")


def shown(args: dict[str, object], kinds: Kinds | None = None) -> dict[str, str]:
    """Each argument's text in a request."""
    return dict(args_text(args, kinds or Kinds()))


# llm-rewrite-object-fields-request-shows-a-seed-named-object
@pytest.mark.parametrize("named", ["m::Order", "Order", "pkg.m::Order"])
def test_a_seed_form_shows_the_class_it_names_and_its_other_keys(named: str) -> None:
    form = {"__class__": named, "code": "0", "tags": [1, None]}

    assert shown({"o": form}) == {
        "o": '<Order object, built from {"code": "0", "tags": [1, null]}>'
    }


def test_a_form_s_positional_arguments_are_shown_as_the_form_holds_them() -> None:
    form = {"__class__": "m::Order", "__args__": ["0"]}

    assert shown({"o": form}) == {"o": '<Order object, built from {"__args__": ["0"]}>'}


def test_a_list_a_class_hint_builds_from_is_shown_as_the_list() -> None:
    kinds = Kinds.of_seed(Seed.of({"o": ["0"]}, {"o": Builds(Order)}))

    assert shown({"o": ["0"]}, kinds) == {"o": '<Order object, built from ["0"]>'}


def test_arguments_that_are_no_plain_data_show_the_class_alone_and_run_no_code() -> None:
    form = {"__class__": "m::Order", "code": Code("0")}

    assert shown({"o": form}) == {"o": "<Order object>"}


def test_arguments_json_cannot_hold_show_the_class_alone() -> None:
    form = {"__class__": "m::Order", "codes": {(1, 2): "0"}}

    assert shown({"o": form}) == {"o": "<Order object>"}


def test_arguments_too_long_for_a_value_show_the_class_alone() -> None:
    form = {"__class__": "m::Order", "code": "x" * VALUE_SIZE}

    assert shown({"o": form}) == {"o": "<Order object>"}


def test_a_dict_under_self_with_no_class_known_holds_an_object() -> None:
    assert shown({"self": {"code": "0"}}, Kinds(self_name="self")) == {"self": "<holds an object>"}


def test_a_dict_under_a_hint_that_names_no_one_class_holds_an_object() -> None:
    kinds = Kinds({"o": NoOneClass("abstract", (Order,))})

    assert shown({"o": {"code": "0"}}, kinds) == {"o": "<holds an object>"}


def test_a_class_name_that_is_not_text_holds_an_object() -> None:
    assert shown({"o": {"__class__": 1, "code": "0"}}) == {"o": "<holds an object>"}

import inspect

import pytest

from pyct.cli import (
    UsageError,
    check_seed_fits,
    check_seed_types,
    check_spec,
    contradictions,
    parse_budget,
    parse_command,
    parse_plateau,
    parse_seed,
    plain_annotations,
)
from pyct.config.budget import Budget
from pyct.config.plateau import Plateau
from pyct.run.target import Target


def classify(x: int) -> str:
    return "positive" if x > 0 else "other"


SIGNATURE = inspect.signature(classify)


def four_plain_types(s: str, n: int, x: float, b: bool) -> str:
    return f"{s}{n}{x}{b}"


def not_plain(s: str | None, xs: list[int], c: Target) -> None:
    return None


def no_annotation(s) -> None:
    return None


def stored_as_text(s: str, missing: object) -> None:
    return None


# what ``from __future__ import annotations`` leaves behind: the text, unresolved
stored_as_text.__annotations__ = {"s": "str", "missing": "Missing", "return": "None"}


def target_for(fn: object) -> Target:
    """A Target around ``fn``; only ``fn`` matters to the seed-type check."""
    assert callable(fn)
    return Target(spec="m::f", fn=fn, file="m.py", signature=inspect.signature(fn))


def test_plain_annotations_keeps_the_four_plain_types() -> None:
    assert plain_annotations(four_plain_types) == {"s": str, "n": int, "x": float, "b": bool}


def test_plain_annotations_skips_the_return() -> None:
    assert "return" not in plain_annotations(four_plain_types)


def test_plain_annotations_skips_an_annotation_that_is_not_plain() -> None:
    assert plain_annotations(not_plain) == {}


def test_plain_annotations_skips_a_parameter_with_no_annotation() -> None:
    assert plain_annotations(no_annotation) == {}


def test_plain_annotations_resolves_text_and_skips_only_what_it_cannot() -> None:
    # one bad name costs that parameter alone, not the whole function
    assert plain_annotations(stored_as_text) == {"s": str}


def test_contradictions_names_the_parameter_the_type_and_the_value() -> None:
    assert contradictions({"s": str}, {"s": 5}) == ["s must be a str, got 5"]


def test_contradictions_spells_the_value_as_json() -> None:
    assert contradictions({"n": int}, {"n": "5"}) == ['n must be an int, got "5"']


def test_contradictions_says_an_before_int() -> None:
    assert contradictions({"n": int}, {"n": 1.5}) == ["n must be an int, got 1.5"]


def test_contradictions_follows_python_on_numbers() -> None:
    # bool is an int to Python, and an int is accepted where a float is asked for
    assert contradictions({"n": int, "x": float, "y": float}, {"n": True, "x": 3, "y": False}) == []


def test_contradictions_refuses_an_int_for_a_bool() -> None:
    assert contradictions({"b": bool}, {"b": 1}) == ["b must be a bool, got 1"]


def test_contradictions_refuses_none_for_every_plain_type() -> None:
    hints = {"s": str, "n": int, "x": float, "b": bool}
    assert contradictions(hints, dict.fromkeys(hints)) == [
        "s must be a str, got null",
        "n must be an int, got null",
        "x must be a float, got null",
        "b must be a bool, got null",
    ]


def test_contradictions_keeps_the_signature_order() -> None:
    assert contradictions({"name": str, "age": int}, {"age": "x", "name": 5}) == [
        "name must be a str, got 5",
        'age must be an int, got "x"',
    ]


def test_contradictions_ignores_a_parameter_the_seed_does_not_name() -> None:
    assert contradictions({"s": str}, {}) == []


def test_contradictions_accepts_a_matching_seed() -> None:
    assert contradictions({"s": str, "n": int}, {"s": "abc", "n": 1}) == []


def test_check_seed_types_raises_one_line_per_contradiction() -> None:
    with pytest.raises(UsageError) as raised:
        check_seed_types(target_for(four_plain_types), {"s": 5, "n": "5", "x": 1, "b": True})

    assert str(raised.value) == 's must be a str, got 5\nn must be an int, got "5"'


def test_check_seed_types_accepts_a_matching_seed() -> None:
    check_seed_types(target_for(four_plain_types), {"s": "a", "n": 1, "x": 1.5, "b": True})


@pytest.mark.parametrize(
    "spec",
    [
        "mod.f",
        "::f",
        "mod::",
        "a::b::c",
        "mod/f.py::f",
        "mod.py::f",
        "my mod::f",
        "my-mod::f",
        "mod::f g",
        "pkg..mod::f",
        "mod::1f",
    ],
)
def test_check_spec_refuses_anything_but_module_function(spec: str) -> None:
    with pytest.raises(UsageError, match="MODULE::FUNCTION"):
        check_spec(spec)


def test_check_spec_accepts_a_dotted_module() -> None:
    check_spec("pkg.mod::f")


def test_check_spec_accepts_underscores_and_digits() -> None:
    check_spec("_private.mod2::f_2")


@pytest.mark.parametrize("text", ["[1]", "1", '"x"', "null", "not json", ""])
def test_parse_seed_refuses_anything_but_an_object(text: str) -> None:
    with pytest.raises(UsageError, match="JSON object"):
        parse_seed(text)


def test_parse_seed_returns_the_object() -> None:
    assert parse_seed('{"x": 1, "s": "a"}') == {"x": 1, "s": "a"}


def test_check_seed_fits_refuses_an_unexpected_key() -> None:
    with pytest.raises(UsageError, match="y"):
        check_seed_fits(SIGNATURE, {"y": 1})


def test_check_seed_fits_refuses_a_missing_key() -> None:
    with pytest.raises(UsageError, match="x"):
        check_seed_fits(SIGNATURE, {})


def test_check_seed_fits_accepts_a_fitting_seed() -> None:
    check_seed_fits(SIGNATURE, {"x": 1})


def test_check_seed_fits_ignores_the_value_type() -> None:
    # names only: a wrong-typed value is the target's business, not the command line's
    check_seed_fits(SIGNATURE, {"x": "a"})


def test_parse_command_refuses_the_seed_twice() -> None:
    with pytest.raises(UsageError, match="once"):
        parse_command(["run", "m::f", "{}", "--args", "{}"])


def test_parse_budget_returns_the_seconds() -> None:
    assert parse_budget("1.5") == Budget(seconds=1.5)


def test_parse_budget_without_the_flag_is_no_deadline() -> None:
    assert parse_budget(None) == Budget()


@pytest.mark.parametrize("text", ["0", "-1", "abc", "", "1s", "nan", "inf", "1e400"])
def test_parse_budget_refuses_anything_but_a_positive_number(text: str) -> None:
    with pytest.raises(UsageError, match="budget"):
        parse_budget(text)


def test_parse_plateau_returns_the_inputs() -> None:
    assert parse_plateau("3") == Plateau(inputs=3)
    # int() reads an optional sign, so a signed whole number is a whole number
    assert parse_plateau("+3") == Plateau(inputs=3)


def test_parse_plateau_without_the_flag_is_no_plateau_stop() -> None:
    assert parse_plateau(None) == Plateau()


@pytest.mark.parametrize("text", ["0", "-1", "2.5", "1.0", "1e2", "abc", "", "3 inputs"])
def test_parse_plateau_refuses_anything_but_a_whole_number_above_zero(text: str) -> None:
    with pytest.raises(UsageError, match="plateau must be a whole number above zero"):
        parse_plateau(text)

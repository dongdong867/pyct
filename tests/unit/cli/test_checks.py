import inspect

import pytest

from pyct.cli import (
    UsageError,
    check_seed_fits,
    check_spec,
    parse_budget,
    parse_command,
    parse_seed,
)
from pyct.config.budget import Budget


def classify(x: int) -> str:
    return "positive" if x > 0 else "other"


SIGNATURE = inspect.signature(classify)


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

import inspect

import pytest

from pyct.cli import UsageError, check_seed_fits, check_spec, parse_command, parse_seed


def classify(x: int) -> str:
    return "positive" if x > 0 else "other"


SIGNATURE = inspect.signature(classify)


@pytest.mark.parametrize("spec", ["mod.f", "::f", "mod::", "a::b::c", "mod/f.py::f", "mod.py::f"])
def test_check_spec_refuses_anything_but_module_function(spec: str) -> None:
    with pytest.raises(UsageError, match="MODULE::FUNCTION"):
        check_spec(spec)


def test_check_spec_accepts_a_dotted_module() -> None:
    check_spec("pkg.mod::f")


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

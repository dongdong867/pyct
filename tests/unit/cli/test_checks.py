import pytest

from pyct.cli import UsageError, check_spec, parse_command


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


def test_parse_command_refuses_the_seed_twice() -> None:
    with pytest.raises(UsageError, match="once"):
        parse_command(["run", "m::f", "{}", "--args", "{}"])

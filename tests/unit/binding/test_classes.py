"""Reading a ``"__class__"`` text into the class it names, and why one names none."""

import datetime
import importlib
import inspect

import pytest

from pyct.binding import classes
from pyct.binding.classes import ClassNameError, load_class, signature_of
from tests.unit.binding import named_classes

HOME = "tests.unit.binding.named_classes"


def reason(text: object, home: str = HOME) -> str:
    """Why ``text`` names no class, as the error says it."""
    with pytest.raises(ClassNameError) as raised:
        load_class(text, home)
    return raised.value.reason


def imported(module: str) -> BaseException:
    """What plain Python's import of ``module`` raises in this run."""
    try:
        importlib.import_module(module)
    except (Exception, SystemExit) as error:
        return error
    raise AssertionError(f"{module} imported")


def test_a_module_and_a_name_read_the_class_there() -> None:
    assert load_class("datetime::date", HOME) is datetime.date


def test_a_bare_name_is_read_in_the_home_module() -> None:
    assert load_class("Outer", HOME) is named_classes.Outer


def test_each_dotted_part_is_read_in_turn() -> None:
    assert load_class(f"{HOME}::Outer.Inner", "json") is named_classes.Outer.Inner
    assert load_class("Outer.Inner", HOME) is named_classes.Outer.Inner


def test_a_module_that_does_not_import_says_what_its_import_raised() -> None:
    missing = "tests.unit.binding.nowhere"

    assert reason(f"{missing}::Outer") == f"cannot import {missing}: {imported(missing)!r}"


def test_a_system_exit_at_import_is_a_module_that_does_not_import() -> None:
    module = "tests.unit.binding.exits_on_import"

    assert reason(f"{module}::Outer") == f"cannot import {module}: {imported(module)!r}"


def test_a_name_the_module_lacks_is_no_class_of_it() -> None:
    assert reason(f"{HOME}::Outr") == f"{HOME} has no class Outr"
    assert reason("Outer.Innr") == f"{HOME} has no class Outer.Innr"


def test_a_name_that_is_not_a_class_says_so() -> None:
    assert reason("helper") == f"{HOME}::helper is not a class"


def test_a_name_whose_read_raises_says_what_it_raised() -> None:
    module = "tests.unit.binding.unreadable_names"

    assert reason(f"{module}::Thing") == (
        f"cannot read {module}::Thing: {RuntimeError('cannot give Thing')!r}"
    )


@pytest.mark.parametrize(
    "text",
    [
        "datetime:date",
        "::date",
        "datetime::",
        "datetime::date::x",
        "date.",
        "a..b::date",
        "",
        "two words",
    ],
)
def test_a_badly_written_name_is_written_back_as_json(text: str) -> None:
    assert reason(text) == f"'__class__' must be MODULE::CLASS or a class name, got \"{text}\""


def test_a_value_that_is_not_a_str_is_written_back_as_json() -> None:
    assert reason(5) == "'__class__' must be MODULE::CLASS or a class name, got 5"
    assert reason(["a"]) == "'__class__' must be MODULE::CLASS or a class name, got [\"a\"]"


def test_a_value_json_cannot_write_is_written_as_its_repr() -> None:
    # through run(), a caller can hand the class itself
    expected = f"'__class__' must be MODULE::CLASS or a class name, got {datetime.date!r}"

    assert reason(datetime.date) == expected


def test_a_class_s_signature_is_read_once(monkeypatch: pytest.MonkeyPatch) -> None:
    reads: list[object] = []
    real = inspect.signature

    def counted(owner: object) -> inspect.Signature:
        reads.append(owner)
        return real(owner)  # pyrefly: ignore[bad-argument-type]

    class Fresh:
        def __init__(self, a: int) -> None:
            self.a = a

    monkeypatch.setattr(classes.inspect, "signature", counted)

    first = signature_of(Fresh)

    assert first is signature_of(Fresh)
    assert reads == [Fresh]
    assert first is not None
    assert list(first.parameters) == ["a"]


def test_a_signature_python_cannot_read_is_none() -> None:
    # some builds of Python read date's signature, and some cannot
    assert signature_of(datetime.date) == classes.constructor(datetime.date)

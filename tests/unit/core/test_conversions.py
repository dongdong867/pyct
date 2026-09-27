"""What `int(x)`, `float(x)`, `bool(x)` and `map(int, ...)` answer on tracked values."""

import builtins
import math

import pytest

from pyct.core import conversions
from pyct.core.bools import ConcolicBool
from pyct.core.branch import SinkItem
from pyct.core.floats import ConcolicFloat
from pyct.core.ints import ConcolicInt
from pyct.core.strs import ConcolicStr
from pyct.core.values import raised_by_target
from tests.unit.core.test_substitutes import expressions


def text(value: str, sink: list[SinkItem]) -> ConcolicStr:
    return ConcolicStr(value, expression="s", sink=sink)


def test_int_of_a_tracked_int_and_float_of_a_tracked_float_are_the_values_themselves() -> None:
    sink: list[SinkItem] = []
    n = ConcolicInt(3, expression="n", sink=sink)
    f = ConcolicFloat(2.5, expression="f", sink=sink)
    b = ConcolicBool(True, expression=[">", "x", 0], sink=sink)

    assert conversions.int_of(n) is n
    assert conversions.float_of(f) is f
    assert conversions.bool_of(b) is b
    assert sink == []


@pytest.mark.parametrize(
    ("convert", "value", "answer", "expression"),
    [
        (conversions.int_of, True, 1, ["int", [">", "x", 0]]),
        (conversions.int_of, False, 0, ["int", [">", "x", 0]]),
        (conversions.float_of, True, 1.0, ["float", [">", "x", 0]]),
    ],
)
def test_a_tracked_bool_converts_to_the_number_it_is(
    convert: object, value: bool, answer: object, expression: object
) -> None:
    sink: list[SinkItem] = []

    result = convert(ConcolicBool(value, expression=[">", "x", 0], sink=sink))  # pyrefly: ignore

    assert (type(result), repr(result), result.expression) == (
        ConcolicInt if isinstance(answer, int) else ConcolicFloat,
        repr(answer),
        expression,
    )
    assert sink == []


def test_float_of_a_tracked_int_rounds_it_as_python_does() -> None:
    sink: list[SinkItem] = []

    result = conversions.float_of(ConcolicInt(2**53 + 1, expression="n", sink=sink))

    assert (type(result), repr(result), result.expression) == (
        ConcolicFloat,
        repr(2.0**53),
        ["float", "n"],
    )


def test_float_of_a_tracked_int_too_large_raises_python_s_error_as_the_target_s() -> None:
    with pytest.raises(OverflowError) as raised:
        conversions.float_of(ConcolicInt(10**400, expression="n", sink=[]))

    assert raised_by_target(raised.value)


def test_int_of_a_tracked_float_cuts_it_toward_zero_after_its_finite_fork() -> None:
    sink: list[SinkItem] = []

    result = conversions.int_of(ConcolicFloat(-2.5, expression="f", sink=sink))

    assert (type(result), repr(result), result.expression) == (ConcolicInt, "-2", ["int", "f"])
    assert expressions(sink) == [(["isfinite", "f"], True)]


@pytest.mark.parametrize(("value", "error"), [(math.nan, ValueError), (math.inf, OverflowError)])
def test_int_of_a_float_python_cannot_convert_raises_past_its_fork(
    value: float, error: type[Exception]
) -> None:
    sink: list[SinkItem] = []

    with pytest.raises(error) as raised:
        conversions.int_of(ConcolicFloat(value, expression="f", sink=sink))

    assert str(raised.value) == _message(int, value)
    assert raised_by_target(raised.value)
    assert expressions(sink) == [(["isfinite", "f"], False)]


def _message(convert: type, value: object) -> str:
    """What plain Python says when the conversion refuses the value."""
    try:
        convert(value)
    except (ValueError, OverflowError) as error:
        return str(error)
    raise AssertionError(f"{convert.__name__} took {value!r}")


@pytest.mark.parametrize(("value", "answer"), [("12", 12), (" -1_0 ", -10), ("٣", 3), ("007", 7)])
def test_int_of_a_tracked_str_reads_it_as_python_does_after_its_fork(
    value: str, answer: int
) -> None:
    sink: list[SinkItem] = []

    result = conversions.int_of(text(value, sink))

    assert (type(result), repr(result), result.expression) == (
        ConcolicInt,
        repr(answer),
        ["int", "s"],
    )
    assert expressions(sink) == [(["isint", "s"], True)]


@pytest.mark.parametrize(
    ("convert", "check", "value"),
    [(conversions.int_of, "isint", "1.5"), (conversions.float_of, "isfloat", "abc")],
)
def test_text_python_refuses_raises_its_value_error_past_the_fork(
    convert: object, check: str, value: str
) -> None:
    sink: list[SinkItem] = []

    with pytest.raises(ValueError) as raised:
        convert(text(value, sink))  # pyrefly: ignore[not-callable]

    kind = int if check == "isint" else float
    assert str(raised.value) == _message(kind, value)
    assert raised_by_target(raised.value)
    assert expressions(sink) == [([check, "s"], False)]


def test_float_of_a_tracked_str_reads_it_as_python_does_after_its_fork() -> None:
    sink: list[SinkItem] = []

    result = conversions.float_of(text(" 1_0.5e-1 ", sink))

    assert (type(result), repr(result), result.expression) == (
        ConcolicFloat,
        "1.05",
        ["float", "s"],
    )
    assert expressions(sink) == [(["isfloat", "s"], True)]


@pytest.mark.parametrize(
    ("kind", "value", "false", "answer"),
    [
        (ConcolicInt, 0, 0, False),
        (ConcolicFloat, -0.0, 0.0, False),
        (ConcolicFloat, math.nan, 0.0, True),
        (ConcolicStr, "a", "''", True),
    ],
)
def test_bool_of_a_tracked_value_holds_its_truth_untested(
    kind: type, value: object, false: object, answer: bool
) -> None:
    sink: list[SinkItem] = []

    result = conversions.bool_of(kind(value, expression="x", sink=sink))

    assert (type(result), repr(result), result.expression) == (
        ConcolicBool,
        repr(answer),
        ["!=", "x", false],
    )
    assert sink == []


def test_int_of_a_tracked_str_in_another_form_is_python_s_answer_and_a_downgrade() -> None:
    sink: list[SinkItem] = []

    assert repr(conversions.int_in_another_form(text("ff", sink), 16)) == "255"
    assert repr(conversions.int_in_another_form(text("10", sink), base=2)) == "2"
    assert expressions(sink) == ["int", "int"]


def test_int_in_another_form_that_raises_records_nothing_and_raises_as_the_target_s() -> None:
    sink: list[SinkItem] = []

    with pytest.raises(ValueError) as raised:
        conversions.int_in_another_form(text("zz", sink), 16)

    assert raised_by_target(raised.value)
    assert sink == []


def test_a_conversion_is_picked_only_for_python_s_own_builtin_and_a_tracked_argument() -> None:
    s = text("1", [])

    assert conversions.picked(int, (s,), {}) is conversions.int_of
    assert conversions.picked(float, (s,), {}) is conversions.float_of
    assert conversions.picked(bool, (s,), {}) is conversions.bool_of
    assert conversions.picked(int, (s, 16), {}) is conversions.int_in_another_form
    assert conversions.picked(int, (), {"x": s}) is None
    assert conversions.picked(float, (s, 2), {}) is None
    assert conversions.picked(int, ("1",), {}) is None
    assert conversions.picked(int, (s,), {"base": 10}) is conversions.int_in_another_form
    assert conversions.picked(lambda value: 7, (s,), {}) is None
    assert conversions.picked(str, (s,), {}) is None


def test_map_with_a_conversion_first_converts_each_item_lazily() -> None:
    sink: list[SinkItem] = []
    mapped = conversions.picked(map, (int, [text("1", sink), text("2", sink)]), {})
    assert mapped is not None

    items = mapped(int, [text("1", sink), text("2", sink)])

    assert type(items) is map
    assert sink == []
    assert [repr(item) for item in items] == ["1", "2"]
    assert expressions(sink) == [(["isint", "s"], True)] * 2


def test_map_with_a_conversion_on_plain_items_is_python_s_own() -> None:
    mapped = conversions.picked(map, (float, ["1.5", 2]), {})
    assert mapped is not None

    assert list(mapped(float, ["1.5", 2])) == [1.5, 2.0]
    with pytest.raises(ValueError) as raised:
        list(mapped(int, ["x"]))
    assert raised_by_target(raised.value)
    with pytest.raises(TypeError) as refused:
        mapped(int, 5)
    assert raised_by_target(refused.value)


def test_map_with_anything_else_first_is_not_picked() -> None:
    assert conversions.picked(map, (str, ["a"]), {}) is None
    assert conversions.picked(map, (), {}) is None
    assert conversions.picked(builtins.len, ("a",), {}) is None


@pytest.mark.parametrize(
    ("convert", "value"),
    [
        (conversions.int_of, 5),
        (conversions.float_of, "5"),
        (conversions.bool_of, 5),
        (conversions.int_in_another_form, "5"),
    ],
)
def test_a_conversion_handed_a_value_it_does_not_take_is_a_pyct_bug(
    convert: object, value: object
) -> None:
    with pytest.raises(TypeError, match="pyct") as raised:
        convert(value)  # pyrefly: ignore[not-callable]

    assert not raised_by_target(raised.value)

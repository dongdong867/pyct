"""What a call of a `math` function answers where the target writes it, given a tracked number."""

import math
from collections.abc import Callable
from typing import Any

import pytest

from pyct.core import math_calls, substitutes
from pyct.core.bools import ConcolicBool
from pyct.core.branch import SinkItem
from pyct.core.floats import ConcolicFloat
from pyct.core.ints import ConcolicInt
from pyct.core.strs import ConcolicStr
from pyct.core.values import raised_by_target
from tests.unit.core.test_substitutes import expressions


def called(function: Callable[..., object]) -> Callable[..., Any]:
    """What a call written with the function's name calls, as substituted code asks for it."""
    return substitutes.call(function)


def tracked(value: float, sink: list[SinkItem], name: str = "x") -> ConcolicFloat:
    return ConcolicFloat(value, expression=name, sink=sink)


# the plain value each named operand below holds
PLAIN: dict[str, Any] = {"x": 1.5, "y": -0.0, "n": 4, "b": True, "s": "a"}


def operands(names: tuple[Any, ...], sink: list[SinkItem]) -> tuple[list[Any], list[Any]]:
    """Each operand as the call is handed it, a name as a tracked value, and as plain Python has it.

    A name is a tracked value holding its `PLAIN` value; anything else stands for itself.
    """
    values: dict[str, Any] = {
        "x": tracked(1.5, sink),
        "y": tracked(-0.0, sink, "y"),
        "n": ConcolicInt(4, expression="n", sink=sink),
        "b": ConcolicBool(True, expression=[">", "n", 0], sink=sink),
        "s": ConcolicStr("a", expression="s", sink=sink),
    }
    written = [values.get(name, name) if isinstance(name, str) else name for name in names]
    plain = [PLAIN.get(name, name) if isinstance(name, str) else name for name in names]
    return written, plain


def _message(function: Callable[..., object], *args: object, **kwargs: object) -> str:
    """What plain Python says when the call raises."""
    try:
        function(*args, **kwargs)
    except Exception as error:
        return str(error)
    raise AssertionError("the call did not raise")


@pytest.mark.parametrize(
    ("function", "head", "value"),
    [
        (math.fabs, "fabs", -2.5),
        (math.isnan, "isnan", math.nan),
        (math.isinf, "isinf", -math.inf),
        (math.isfinite, "isfinite", 1e300),
    ],
)
def test_a_function_of_one_float_answers_python_s_result_tracked(
    function: Callable[[float], object], head: str, value: float
) -> None:
    sink: list[SinkItem] = []

    result = called(function)(tracked(value, sink))

    answer = function(value)
    kind = ConcolicBool if isinstance(answer, bool) else ConcolicFloat
    assert (type(result), repr(result)) == (kind, repr(answer))
    assert result.expression == [head, "x"]
    # a tracked bool's fork is recorded where the target tests it
    assert sink == []


@pytest.mark.parametrize("value", [4.0, 0.0, -0.0, math.nan, math.inf])
def test_sqrt_records_its_fork_before_it_runs_taken_true_when_it_does_not_raise(
    value: float,
) -> None:
    sink: list[SinkItem] = []

    result = called(math.sqrt)(tracked(value, sink))

    assert repr(result) == repr(math.sqrt(value))
    assert expressions(sink) == [(["not", ["<", "x", 0.0]], True)]


@pytest.mark.parametrize("value", [-1.0, -5e-324, -math.inf])
def test_sqrt_below_zero_raises_python_s_error_past_its_fork(value: float) -> None:
    sink: list[SinkItem] = []

    with pytest.raises(ValueError) as raised:
        called(math.sqrt)(tracked(value, sink))

    assert str(raised.value) == _message(math.sqrt, value)
    assert raised_by_target(raised.value)
    assert expressions(sink) == [(["not", ["<", "x", 0.0]], False)]


def test_a_tracked_int_is_read_as_the_double_python_converts_it_to() -> None:
    sink: list[SinkItem] = []

    result = called(math.sqrt)(ConcolicInt(2**53 + 1, expression="n", sink=sink))

    assert (type(result), repr(result)) == (ConcolicFloat, repr(math.sqrt(2**53 + 1)))
    assert result.expression == ["sqrt", "n"]
    # no `__float__`: the int is read as it is
    assert expressions(sink) == [(["not", ["<", "n", 0.0]], True)]


def test_a_tracked_int_too_large_for_a_double_raises_python_s_error() -> None:
    with pytest.raises(OverflowError) as raised:
        called(math.fabs)(ConcolicInt(10**400, expression="n", sink=[]))

    assert str(raised.value) == _message(math.fabs, 10**400)
    assert raised_by_target(raised.value)


@pytest.mark.parametrize(
    ("args", "expression"),
    [
        (("x", 1.0), ["copysign", "x", 1.0]),
        ((1.0, "x"), ["copysign", 1.0, "x"]),
        ((1.0, "y"), ["copysign", 1.0, "y"]),
        (("x", "y"), ["copysign", "x", "y"]),
        (("x", -2), ["copysign", "x", -2]),
        (("n", -1.0), ["copysign", "n", -1.0]),
    ],
)
def test_copysign_takes_a_tracked_number_on_either_side(
    args: tuple[object, ...], expression: object
) -> None:
    sink: list[SinkItem] = []
    written, plain = operands(args, sink)

    result = called(math.copysign)(*written)

    assert (type(result), repr(result)) == (ConcolicFloat, repr(math.copysign(*plain)))
    assert result.expression == expression
    assert sink == []


@pytest.mark.parametrize(
    ("kwargs", "expression"),
    [
        ({}, ["isclose", "x", 1.5000000001, 1e-09, 0.0]),
        ({"rel_tol": 0.5}, ["isclose", "x", 1.5000000001, 0.5, 0.0]),
        ({"abs_tol": 1, "rel_tol": 0}, ["isclose", "x", 1.5000000001, 0.0, 1.0]),
    ],
)
def test_isclose_writes_both_tolerances_whether_the_call_gave_them_or_not(
    kwargs: dict[str, Any], expression: list[object]
) -> None:
    sink: list[SinkItem] = []

    result = called(math.isclose)(tracked(1.5, sink), 1.5000000001, **kwargs)

    answer = math.isclose(1.5, 1.5000000001, **kwargs)
    # read without its truth test, which would record the fork
    assert (type(result), repr(result)) == (ConcolicBool, repr(answer))
    assert result.expression == expression
    assert [type(part) for part in expression[3:]] == [float, float]
    assert sink == []


def test_isclose_with_a_negative_tolerance_raises_python_s_error_and_records_nothing() -> None:
    sink: list[SinkItem] = []

    with pytest.raises(ValueError) as raised:
        called(math.isclose)(tracked(1.0, sink), 1.0, rel_tol=-1.0)

    assert str(raised.value) == _message(math.isclose, 1.0, 1.0, rel_tol=-1.0)
    assert raised_by_target(raised.value)
    assert sink == []


class Own(float):
    """A float of the target's own, which Python's `math` reads as the double it holds."""


@pytest.mark.parametrize(
    ("function", "args", "kwargs"),
    [
        (math.exp, ("x",), {}),
        (math.log, ("x", 10), {}),
        (math.gcd, ("n", 6), {}),
        (math.pow, (2.0, "x"), {}),
        (math.prod, ([1, 2],), {"start": "x"}),
        # a taught function in a form pyct does not encode
        (math.isclose, ("x", 1.0), {"rel_tol": "x"}),
        (math.isclose, ("x", 1.0), {"abs_tol": True}),
        (math.sqrt, ("b",), {}),
        (math.copysign, ("x", True), {}),
    ],
)
def test_any_other_call_with_a_tracked_argument_is_python_s_answer_and_a_downgrade(
    function: Callable[..., object], args: tuple[object, ...], kwargs: dict[str, object]
) -> None:
    sink: list[SinkItem] = []
    written, plain = operands(args, sink)
    given, plain_given = (
        dict(zip(kwargs, part, strict=True)) for part in operands(tuple(kwargs.values()), sink)
    )

    result = called(function)(*written, **given)

    assert type(result) in (float, int, bool)
    assert repr(result) == repr(function(*plain, **plain_given))
    assert expressions(sink) == [function.__name__]


def test_a_float_of_the_target_s_own_beside_a_tracked_number_reads_as_its_double() -> None:
    sink: list[SinkItem] = []

    result = called(math.copysign)(Own(2.0), tracked(-1.0, sink))

    assert repr(result) == "-2.0"
    expression: list[object] = result.expression
    assert expression == ["copysign", 2.0, "x"]
    assert type(expression[1]) is float


@pytest.mark.parametrize(
    ("function", "args"),
    [
        (math.sqrt, ("x", 2.0)),
        (math.exp, ("s",)),
        (math.gcd, ("x", 6)),
        (math.copysign, ("x",)),
        (math.log, ("x", 1.0)),
    ],
)
def test_a_call_python_refuses_raises_python_s_error_and_records_nothing(
    function: Callable[..., object], args: tuple[object, ...]
) -> None:
    sink: list[SinkItem] = []
    written, plain = operands(args, sink)

    with pytest.raises((TypeError, ValueError, ZeroDivisionError)) as raised:
        called(function)(*written)

    assert str(raised.value) == _message(function, *plain)
    assert raised_by_target(raised.value)
    assert sink == []


@pytest.mark.parametrize(
    ("function", "args", "kwargs"),
    [
        (math.sqrt, (2.0,), {}),
        (math.isclose, (1.0, 1.0), {"abs_tol": 0.5}),
        (math.gcd, (4, 6), {}),
        (math.prod, ([1, 2, 3],), {"start": 2}),
    ],
)
def test_a_call_with_no_tracked_argument_is_python_s_own(
    function: Callable[..., object], args: tuple[object, ...], kwargs: dict[str, object]
) -> None:
    assert called(function)(*args, **kwargs) == function(*args, **kwargs)


def test_a_call_python_refuses_with_no_tracked_argument_raises_python_s_error() -> None:
    with pytest.raises(ValueError) as raised:
        called(math.sqrt)(-1.0)

    assert str(raised.value) == _message(math.sqrt, -1.0)


def test_every_math_function_but_the_three_a_number_answers_itself_is_routed() -> None:
    functions = {
        name for name, member in vars(math).items() if callable(member) and not name.startswith("_")
    }

    assert functions - {"floor", "ceil", "trunc"} == math_calls.NAMES
    assert all(called(getattr(math, name)) is not getattr(math, name) for name in math_calls.NAMES)
    # `math.floor` calls the number's own `__floor__`, which follow-floats teaches
    assert all(
        called(getattr(math, name)) is getattr(math, name) for name in ("floor", "ceil", "trunc")
    )


def test_a_name_that_holds_another_function_is_that_function() -> None:
    def sqrt(value: float) -> float:
        return value

    assert called(sqrt) is sqrt

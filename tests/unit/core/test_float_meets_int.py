"""A tracked int meets a float as Python's numbers do, and a float rounds to a tracked int."""

import math
from collections.abc import Callable

import pytest

from pyct.core.bools import ConcolicBool
from pyct.core.branch import Branch, Downgrade, SinkItem, Site
from pyct.core.floats import ConcolicFloat
from pyct.core.ints import ConcolicInt
from pyct.core.values import raised_by_target

# a probe whose text is fixed here, so the line and column of a fork are exact
PROBE_SITE = Site(file="<probe>", line=2, col=11)

# an int meeting a plain float: the call, and the node it builds in Python's written order
PROMOTED: dict[str, tuple[Callable[[int], object], list[object]]] = {
    "n + 0.5": (lambda n: n + 0.5, ["+", "n", 0.5]),
    "n - 0.5": (lambda n: n - 0.5, ["-", "n", 0.5]),
    "n * 0.1": (lambda n: n * 0.1, ["*", "n", 0.1]),
    "n / 2.0": (lambda n: n / 2.0, ["/", "n", 2.0]),
    "n // 2.5": (lambda n: n // 2.5, ["//", "n", 2.5]),
    "n % 2.5": (lambda n: n % 2.5, ["%", "n", 2.5]),
}

# an int compared with a plain float: the call, and the node
COMPARED: dict[str, tuple[Callable[[int], object], list[object]]] = {
    "n < 2.5": (lambda n: n < 2.5, ["<", "n", 2.5]),
    "n == 3.0": (lambda n: n == 3.0, ["==", "n", 3.0]),
    "n >= 3.0": (lambda n: n >= 3.0, [">=", "n", 3.0]),
}

# a float rounded to an int: the call, and the head its node has
ROUNDINGS: dict[str, tuple[Callable[[float], object], str]] = {
    "math.floor": (math.floor, "floor"),
    "math.ceil": (math.ceil, "ceil"),
    "math.trunc": (math.trunc, "trunc"),
    "round": (round, "round"),
}


def _probe(source: str) -> Callable[..., object]:
    namespace: dict[str, object] = {"math": math}
    exec(compile(source, "<probe>", "exec"), namespace)
    probe = namespace["probe"]
    assert callable(probe)
    return probe


@pytest.mark.parametrize(("call", "expression"), PROMOTED.values(), ids=list(PROMOTED))
def test_an_int_meeting_a_float_is_a_tracked_float_on_pythons_answer(
    call: Callable[[int], object], expression: list[object]
) -> None:
    sink: list[SinkItem] = []
    n = ConcolicInt.made(3, expression="n", sink=sink)

    result = call(n)

    assert type(result) is ConcolicFloat
    assert repr(result) == repr(call(3))
    assert result.expression == expression
    # a plain divisor has nothing to flip, so no zero fork either
    assert sink == []


@pytest.mark.parametrize(("call", "expression"), COMPARED.values(), ids=list(COMPARED))
def test_an_int_compared_with_a_float_is_a_tracked_bool(
    call: Callable[[int], object], expression: list[object]
) -> None:
    sink: list[SinkItem] = []
    n = ConcolicInt.made(3, expression="n", sink=sink)

    result = call(n)

    assert isinstance(result, ConcolicBool)
    assert result.expression == expression
    assert int.__bool__(result) is call(3)
    assert sink == []


def test_a_reflected_operation_keeps_the_written_order() -> None:
    n = ConcolicInt.made(3, expression="n", sink=[])

    # what Python calls when a float subclass on the left hands the sum over to the int
    result = n.__radd__(0.5)

    assert type(result) is ConcolicFloat
    assert result.expression == ["+", 0.5, "n"]
    assert repr(result) == "3.5"


def test_a_plain_float_on_the_left_is_floats_own_and_records_nothing() -> None:
    sink: list[SinkItem] = []
    n = ConcolicInt.made(3, expression="n", sink=sink)

    # float's own compare takes any int and never asks it, so nothing of the int's runs
    result = 2.5 < n  # noqa: SIM300 - the plain float on the left is the point

    assert result is True
    assert sink == []


def test_an_int_meeting_a_tracked_float_keeps_both_conditions() -> None:
    sink: list[SinkItem] = []
    n = ConcolicInt.made(3, expression="n", sink=sink)
    x = ConcolicFloat.made(0.5, expression="x", sink=sink)

    total = n + x
    halves = divmod(n, x)

    assert type(total) is ConcolicFloat and total.expression == ["+", "n", "x"]
    assert [part.expression for part in halves] == [["//", "n", "x"], ["%", "n", "x"]]
    assert repr(halves) == repr(divmod(3, 0.5))
    # one divmod divides once, and records the zero fork of its tracked divisor once
    assert [(item.expression, item.taken) for item in sink if isinstance(item, Branch)] == [
        (["!=", "x", 0.0], True)
    ]
    assert len(sink) == 1


def test_a_float_subclass_that_keeps_floats_own_reads_as_its_value() -> None:
    class Reading(float):
        pass

    n = ConcolicInt.made(3, expression="n", sink=[])

    result = n * Reading(0.5)

    assert type(result) is ConcolicFloat
    assert result.expression == ["*", "n", 0.5]
    assert isinstance(result.expression, list) and type(result.expression[2]) is float


def test_true_division_between_ints_records_the_zero_fork_first() -> None:
    sink: list[SinkItem] = []
    n = ConcolicInt.made(7, expression="n", sink=sink)
    m = ConcolicInt.made(2, expression="m", sink=sink)

    result = _probe("def probe(a, b):\n    return a / b\n")(n, m)

    assert type(result) is ConcolicFloat
    assert result.expression == ["/", "n", "m"]
    assert repr(result) == "3.5"
    assert sink == [Branch(expression=["!=", "m", 0], taken=True, site=PROBE_SITE)]


def test_true_division_by_a_zero_int_lists_the_fork_it_died_on() -> None:
    sink: list[SinkItem] = []
    n = ConcolicInt.made(7, expression="n", sink=sink)
    m = ConcolicInt.made(0, expression="m", sink=sink)

    with pytest.raises(ZeroDivisionError) as raised:
        _probe("def probe(a, b):\n    return a / b\n")(n, m)

    assert raised_by_target(raised.value)
    assert sink == [Branch(expression=["!=", "m", 0], taken=False, site=PROBE_SITE)]


def test_a_reflected_true_division_forks_on_the_tracked_divisor() -> None:
    sink: list[SinkItem] = []
    n = ConcolicInt.made(4, expression="n", sink=sink)

    result = _probe("def probe(b):\n    return 2 / b\n")(n)

    assert type(result) is ConcolicFloat and result.expression == ["/", 2, "n"]
    assert sink == [Branch(expression=["!=", "n", 0], taken=True, site=PROBE_SITE)]


def test_an_int_dividend_over_a_tracked_float_forks_on_the_float() -> None:
    sink: list[SinkItem] = []
    x = ConcolicFloat.made(-0.0, expression="x", sink=sink)

    # -0.0 is a zero divisor, so the fork is taken false and Python raises
    with pytest.raises(ZeroDivisionError) as raised:
        _probe("def probe(b):\n    return 1 / b\n")(x)

    assert raised_by_target(raised.value)
    assert sink == [Branch(expression=["!=", "x", 0.0], taken=False, site=PROBE_SITE)]


def test_a_float_over_a_tracked_int_forks_on_the_int() -> None:
    sink: list[SinkItem] = []
    x = ConcolicFloat.made(7.5, expression="x", sink=sink)
    n = ConcolicInt.made(2, expression="n", sink=sink)

    quotient = x // n
    remainder = x % n

    assert isinstance(quotient, ConcolicFloat) and isinstance(remainder, ConcolicFloat)
    assert (quotient.expression, remainder.expression) == (["//", "x", "n"], ["%", "x", "n"])
    assert (repr(quotient), repr(remainder)) == ("3.0", "1.5")
    assert [item.expression for item in sink if isinstance(item, Branch)] == [["!=", "n", 0]] * 2


def test_an_int_too_large_for_a_float_raises_pythons_own_overflow() -> None:
    sink: list[SinkItem] = []
    n = ConcolicInt.made(10**400, expression="n", sink=sink)

    with pytest.raises(OverflowError) as raised:
        _ = n + 0.5

    assert raised_by_target(raised.value)
    assert sink == []


@pytest.mark.parametrize(("call", "head"), ROUNDINGS.values(), ids=list(ROUNDINGS))
def test_a_rounding_is_a_tracked_int_after_its_finite_fork(
    call: Callable[[float], object], head: str
) -> None:
    sink: list[SinkItem] = []
    x = ConcolicFloat.made(-2.5, expression="x", sink=sink)

    result = _probe("def probe(f, r):\n    return r(f)\n")(x, call)

    assert type(result) is ConcolicInt
    assert result.expression == [head, "x"]
    assert int(int.__index__(result)) == call(-2.5)
    assert sink == [Branch(expression=["isfinite", "x"], taken=True, site=PROBE_SITE)]


@pytest.mark.parametrize(
    ("value", "error"), [(math.nan, ValueError), (math.inf, OverflowError)], ids=["nan", "inf"]
)
@pytest.mark.parametrize(("call", "head"), ROUNDINGS.values(), ids=list(ROUNDINGS))
def test_a_value_that_cannot_round_lists_the_fork_it_died_on(
    call: Callable[[float], object], head: str, value: float, error: type[Exception]
) -> None:
    sink: list[SinkItem] = []
    x = ConcolicFloat.made(value, expression="x", sink=sink)

    with pytest.raises(error) as raised:
        _probe("def probe(f, r):\n    return r(f)\n")(x, call)

    assert raised_by_target(raised.value)
    assert sink == [Branch(expression=["isfinite", "x"], taken=False, site=PROBE_SITE)]


def test_round_half_to_even_is_pythons() -> None:
    x = ConcolicFloat.made(2.5, expression="x", sink=[])

    assert int.__index__(round(x)) == 2
    assert round(x, None).expression == ["round", "x"]


def test_round_to_digits_is_a_downgrade() -> None:
    sink: list[SinkItem] = []
    x = ConcolicFloat.made(2.675, expression="x", sink=sink)

    result = round(x, 2)

    assert type(result) is float and result == round(2.675, 2)
    assert sink == [Downgrade(name="__round__")]


def test_round_with_a_form_float_refuses_raises_its_own_error() -> None:
    sink: list[SinkItem] = []
    x = ConcolicFloat.made(2.5, expression="x", sink=sink)

    # float's own `__round__` takes no keyword, so it raises, and the raise is the target's
    with pytest.raises(TypeError) as raised:
        x.__round__(ndigits=1)  # pyrefly: ignore[unexpected-keyword]

    assert raised_by_target(raised.value)
    assert sink == []

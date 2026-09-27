import math
from collections.abc import Callable

import pytest

from pyct.core.bools import ConcolicBool
from pyct.core.branch import Branch, Downgrade, SinkItem, Site
from pyct.core.floats import ConcolicFloat
from pyct.core.values import raised_by_target

# each taught arithmetic operation with a plain float: the call, and the node it builds. Each
# keeps Python's written order, so a reflected one reads as the target wrote it
ARITHMETIC: dict[str, tuple[Callable[[float], object], list[object]]] = {
    "x + 0.1": (lambda x: x + 0.1, ["+", "x", 0.1]),
    "0.1 + x": (lambda x: 0.1 + x, ["+", 0.1, "x"]),
    "x - 0.5": (lambda x: x - 0.5, ["-", "x", 0.5]),
    "10.0 - x": (lambda x: 10.0 - x, ["-", 10.0, "x"]),
    "x * 3.0": (lambda x: x * 3.0, ["*", "x", 3.0]),
    "3.0 * x": (lambda x: 3.0 * x, ["*", 3.0, "x"]),
    "x / 3.0": (lambda x: x / 3.0, ["/", "x", 3.0]),
    "x + 1": (lambda x: x + 1, ["+", "x", 1]),
    "1 - x": (lambda x: 1 - x, ["-", 1, "x"]),
    "x / 2": (lambda x: x / 2, ["/", "x", 2]),
    "x // 2.5": (lambda x: x // 2.5, ["//", "x", 2.5]),
    "x % -2.0": (lambda x: x % -2.0, ["%", "x", -2.0]),
    "-x": (lambda x: -x, ["-", "x"]),
    "abs(x)": (lambda x: abs(x), ["abs", "x"]),
}

# probes whose text is fixed here, so the line and column of the zero fork are exact
DIVIDE = "def probe(a, b):\n    return a / b\n"
REFLECTED = "def probe(b):\n    return 7.0 / b\n"
DIVISION_SITE = Site(file="<probe>", line=2, col=11)


def _probe(source: str) -> Callable[..., object]:
    namespace: dict[str, object] = {}
    exec(compile(source, "<probe>", "exec"), namespace)
    probe = namespace["probe"]
    assert callable(probe)
    return probe


@pytest.mark.parametrize(("call", "expression"), ARITHMETIC.values(), ids=list(ARITHMETIC))
def test_a_taught_operation_is_floats_own_answer_carrying_its_node(
    call: Callable[[float], object], expression: list[object]
) -> None:
    sink: list[SinkItem] = []
    x = ConcolicFloat(0.2, expression="x", sink=sink)

    result = call(x)

    assert isinstance(result, ConcolicFloat)
    # float.__repr__ reads the plain value, where `==` on the result would build a compare
    assert repr(result) == repr(call(0.2))
    assert result.expression == expression
    assert result.sink is sink
    assert sink == []


def test_an_operation_on_two_tracked_floats_takes_both_expressions() -> None:
    sink: list[SinkItem] = []
    x = ConcolicFloat(1.5, expression="x", sink=sink)
    y = ConcolicFloat(2.0, expression="y", sink=sink)

    result = (x + y) * x

    assert isinstance(result, ConcolicFloat)
    assert result.expression == ["*", ["+", "x", "y"], "x"]
    assert repr(result) == repr((1.5 + 2.0) * 1.5)


def test_unary_plus_is_the_value_itself() -> None:
    x = ConcolicFloat(1.5, expression="x", sink=[])

    assert +x is x


def test_an_operand_float_refuses_is_pythons_own_type_error() -> None:
    sink: list[SinkItem] = []
    x = ConcolicFloat(1.5, expression="x", sink=sink)

    with pytest.raises(TypeError, match="unsupported operand"):
        _ = x + "a"  # pyrefly: ignore[unsupported-operation]
    # float answered NotImplemented, which loses no condition
    assert sink == []


def test_a_tracked_divisor_records_its_zero_fork_before_the_division() -> None:
    sink: list[SinkItem] = []
    x = ConcolicFloat(7.0, expression="x", sink=sink)
    y = ConcolicFloat(2.0, expression="y", sink=sink)

    result = _probe(DIVIDE)(x, y)

    assert isinstance(result, ConcolicFloat)
    assert result.expression == ["/", "x", "y"]
    assert sink == [Branch(expression=["!=", "y", 0.0], taken=True, site=DIVISION_SITE)]


def test_a_tracked_divisor_on_the_right_of_a_plain_float_records_its_zero_fork() -> None:
    sink: list[SinkItem] = []
    y = ConcolicFloat(2.0, expression="y", sink=sink)

    result = _probe(REFLECTED)(y)

    assert isinstance(result, ConcolicFloat)
    assert result.expression == ["/", 7.0, "y"]
    assert sink == [Branch(expression=["!=", "y", 0.0], taken=True, site=DIVISION_SITE)]


@pytest.mark.parametrize("zero", [0.0, -0.0])
def test_a_zero_divisor_raises_as_the_target_after_its_fork(zero: float) -> None:
    sink: list[SinkItem] = []
    x = ConcolicFloat(7.0, expression="x", sink=sink)
    y = ConcolicFloat(zero, expression="y", sink=sink)

    with pytest.raises(ZeroDivisionError) as raised:
        _probe(DIVIDE)(x, y)

    assert raised_by_target(raised.value)
    assert sink == [Branch(expression=["!=", "y", 0.0], taken=False, site=DIVISION_SITE)]


def test_a_plain_zero_divisor_raises_as_the_target_with_no_fork() -> None:
    sink: list[SinkItem] = []
    x = ConcolicFloat(7.0, expression="x", sink=sink)

    with pytest.raises(ZeroDivisionError) as raised:
        _ = x / 0.0

    assert raised_by_target(raised.value)
    assert sink == []


@pytest.mark.parametrize(
    ("value", "whole"), [(2.0, True), (-0.0, True), (2.5, False), (math.inf, False)]
)
def test_is_integer_answers_a_tracked_bool(value: float, whole: bool) -> None:
    sink: list[SinkItem] = []
    x = ConcolicFloat(value, expression="x", sink=sink)

    result = x.is_integer()

    assert isinstance(result, ConcolicBool)
    assert result.expression == ["is_integer", "x"]
    assert int.__bool__(result) is whole
    # the answer is tested for truth where the target tests it, not here
    assert sink == []


def test_is_integer_on_nan_is_false() -> None:
    x = ConcolicFloat(math.nan, expression="x", sink=[])

    assert int.__bool__(x.is_integer()) is False


def test_is_integer_given_an_argument_raises_as_the_target() -> None:
    x = ConcolicFloat(2.0, expression="x", sink=[])

    with pytest.raises(TypeError, match="takes no arguments") as raised:
        x.is_integer(1)  # pyrefly: ignore[bad-argument-count]

    assert raised_by_target(raised.value)


class Gauge(float):
    """A float subclass of a library's own, as numpy.float64 is: it answers some reflected
    operations itself, and hands one back to float. It reads the other side through float's
    own method, so pyct records nothing of its own for the read."""

    def __rtruediv__(self, other: float) -> object:  # pyrefly: ignore[bad-override]
        return ("gauge /", float.__float__(other))

    def __radd__(self, other: float) -> object:  # pyrefly: ignore[bad-override]
        return ("gauge +", float.__float__(other))

    def __rmod__(self, other: float) -> object:  # pyrefly: ignore[bad-override]
        return ("gauge %", float.__float__(other))

    def __rpow__(self, other: float, modulus: object = None) -> object:  # pyrefly: ignore[bad-override]
        return ("gauge **", float.__float__(other))

    def __rsub__(self, other: float) -> object:  # pyrefly: ignore[bad-override]
        return NotImplemented

    def __rmul__(self, other: float) -> object:  # pyrefly: ignore[bad-override]
        # the float on the left, handed back as it came: tracked under pyct
        return other


# an operation with a Gauge on the right, and the operation a plain answer is named by
GAUGED: dict[str, tuple[Callable[[float], object], str]] = {
    "x / g": (lambda x: x / Gauge(0.0), "__truediv__"),
    "x + g": (lambda x: x + Gauge(1.0), "__add__"),
    "x % g": (lambda x: x % Gauge(0.0), "__mod__"),
    # a power is one of float's derived downgrades, which ask the subclass first as well
    "x ** g": (lambda x: x ** Gauge(2.0), "__pow__"),
}


@pytest.mark.parametrize(("call", "name"), GAUGED.values(), ids=list(GAUGED))
def test_a_float_subclass_that_answers_the_reflected_operation_answers_first(
    call: Callable[[float], object], name: str
) -> None:
    sink: list[SinkItem] = []
    x = ConcolicFloat(2.5, expression="x", sink=sink)

    # Python asks a float subclass on the right first when it defines the reflected operation,
    # so a plain 2.5 gets the subclass's answer, and so does the tracked one
    assert call(x) == call(2.5)
    # the answer is plain, so x's condition is lost there and the operation is named
    assert sink == [Downgrade(name=name)]


def test_a_tracked_answer_from_a_float_subclass_is_no_downgrade() -> None:
    sink: list[SinkItem] = []
    x = ConcolicFloat(2.5, expression="x", sink=sink)

    result = x * Gauge(1.0)

    assert result is x
    assert sink == []
    assert float.__float__(result) == 2.5 * Gauge(1.0)


def test_a_float_subclass_that_hands_the_reflected_operation_back_gets_floats_answer() -> None:
    sink: list[SinkItem] = []
    x = ConcolicFloat(2.5, expression="x", sink=sink)

    result = x - Gauge(1.0)

    # its `__rsub__` answers NotImplemented, so float's own subtraction answers, followed
    assert isinstance(result, ConcolicFloat)
    assert result.expression == ["-", "x", 1.0]

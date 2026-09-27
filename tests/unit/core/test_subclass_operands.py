"""An operand of the target's own number subclass enters an expression as the plain number.

pyct writes each expression later, for the fork line and the solver, so an operand kept as the
target's object would run the target's own methods inside pyct and write what they return.
"""

from collections.abc import Callable
from enum import IntEnum
from typing import Any

import pytest

from pyct.core.branch import SinkItem
from pyct.core.floats import ConcolicFloat
from pyct.core.ints import ConcolicInt


def _refuse(*_args: object) -> Any:
    raise AssertionError("pyct ran a method of the target's own class")


class Loud(int):
    """An int whose own methods fail the test if anything calls them."""

    __repr__ = __str__ = __format__ = __int__ = __index__ = __float__ = _refuse
    __lt__ = __gt__ = __le__ = __ge__ = __neg__ = __abs__ = _refuse


class Lying(int):
    """An int whose own conversions answer another number than the one it is."""

    def __int__(self) -> int:
        return 99

    def __index__(self) -> int:
        return 99


class Level(IntEnum):
    HIGH = 3


class Gauge(float):
    """A float whose own conversion and text fail the test if anything calls them."""

    __repr__ = __str__ = __format__ = __float__ = __neg__ = __lt__ = _refuse


def _operands(expression: object) -> list[object]:
    """The two operands of a binary expression."""
    assert isinstance(expression, list) and len(expression) == 3, expression
    return expression[1:]


# each operation a tracked int takes an operand in, with the operand on the right
INT_OPERATIONS: dict[str, Callable[[Any, Any], Any]] = {
    "compare": lambda n, other: n > other,
    "equality": lambda n, other: n == other,
    "arithmetic": lambda n, other: n + other,
    "division": lambda n, other: n // other,
    "remainder": lambda n, other: n % other,
    "true-division": lambda n, other: n / other,
}


@pytest.mark.parametrize("operation", INT_OPERATIONS.values(), ids=INT_OPERATIONS.keys())
@pytest.mark.parametrize("other", [Loud(3), Lying(3), Level.HIGH], ids=["loud", "lying", "enum"])
def test_an_int_subclass_beside_a_tracked_int_reads_as_its_plain_int(
    operation: Callable[[Any, Any], Any], other: int
) -> None:
    n = ConcolicInt(7, expression="n", sink=[])

    result = operation(n, other)

    written = _operands(result.expression)[1]
    assert type(written) is int and written == 3


def test_a_divmod_by_an_int_subclass_reads_it_as_its_plain_int() -> None:
    n = ConcolicInt(7, expression="n", sink=[])

    quotient, remainder = divmod(n, Loud(3))

    assert [type(_operands(part.expression)[1]) for part in (quotient, remainder)] == [int, int]


def test_a_reflected_operation_reads_an_int_subclass_as_its_plain_int() -> None:
    n = ConcolicInt(7, expression="n", sink=[])

    # `Loud(3) - n` is int's own and plain, so the reflected method is asked for by name
    result = n.__rsub__(Loud(3))

    assert result.expression == ["-", 3, "n"]
    assert type(result.expression[1]) is int


def test_a_tracked_bool_reads_an_int_subclass_as_its_plain_int() -> None:
    sink: list[SinkItem] = []
    truth = ConcolicInt(7, expression="n", sink=sink) > 0

    result = truth + Loud(2)

    assert result.expression == ["+", [">", "n", 0], 2]
    assert type(_operands(result.expression)[1]) is int


def test_a_tracked_float_reads_an_int_subclass_as_its_plain_int() -> None:
    f = ConcolicFloat(0.5, expression="f", sink=[])

    results: list[Any] = [f + Loud(2), f < Lying(2), f * Level.HIGH]

    assert [_operands(result.expression)[1] for result in results] == [2, 2, 3]
    assert all(type(_operands(result.expression)[1]) is int for result in results)


def test_a_float_subclass_reads_as_its_plain_float_beside_any_tracked_number() -> None:
    n = ConcolicInt(7, expression="n", sink=[])
    f = ConcolicFloat(0.5, expression="f", sink=[])

    results: list[Any] = [n < Gauge(2.5), n + Gauge(2.5), f < Gauge(2.5), f - Gauge(2.5)]

    assert [_operands(result.expression)[1] for result in results] == [2.5] * 4
    assert all(type(_operands(result.expression)[1]) is float for result in results)


def test_a_plain_bool_operand_stays_the_literal_it_is() -> None:
    n = ConcolicInt(7, expression="n", sink=[])

    result = n + True

    assert result.expression == ["+", "n", True]
    assert result.expression[2] is True

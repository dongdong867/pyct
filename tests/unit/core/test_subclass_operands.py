"""An operand of the target's own number subclass enters an expression as the plain number.

pyct writes each expression later, for the fork line and the solver, so an operand kept as the
target's object would run the target's own methods inside pyct and write what they return.
"""

from collections.abc import Callable
from enum import IntEnum, IntFlag
from typing import Any

import pytest

from pyct.core.branch import Downgrade, SinkItem
from pyct.core.floats import ConcolicFloat
from pyct.core.ints import ConcolicInt


def _refuse(*_args: object) -> Any:
    raise AssertionError("pyct ran a method of the target's own class")


class Loud(int):
    """An int whose own methods fail the test if anything calls them.

    It defines no operation Python would ask of it on the right of an int: those run where
    Python runs them (see `Rev`).
    """

    __repr__ = __str__ = __format__ = __int__ = __index__ = __float__ = _refuse
    __neg__ = __abs__ = _refuse


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
    n = ConcolicInt.made(7, expression="n", sink=[])

    result = operation(n, other)

    written = _operands(result.expression)[1]
    assert type(written) is int and written == 3


def test_a_divmod_by_an_int_subclass_reads_it_as_its_plain_int() -> None:
    n = ConcolicInt.made(7, expression="n", sink=[])

    quotient, remainder = divmod(n, Loud(3))

    assert [type(_operands(part.expression)[1]) for part in (quotient, remainder)] == [int, int]


def test_a_reflected_operation_reads_an_int_subclass_as_its_plain_int() -> None:
    n = ConcolicInt.made(7, expression="n", sink=[])

    # `Loud(3) - n` is int's own and plain, so the reflected method is asked for by name
    result = n.__rsub__(Loud(3))

    assert result.expression == ["-", 3, "n"]
    assert type(result.expression[1]) is int


def test_a_tracked_bool_reads_an_int_subclass_as_its_plain_int() -> None:
    sink: list[SinkItem] = []
    truth = ConcolicInt.made(7, expression="n", sink=sink) > 0

    result = truth + Loud(2)

    assert result.expression == ["+", [">", "n", 0], 2]
    assert type(_operands(result.expression)[1]) is int


def test_a_tracked_float_reads_an_int_subclass_as_its_plain_int() -> None:
    f = ConcolicFloat.made(0.5, expression="f", sink=[])

    results: list[Any] = [f + Loud(2), f < Lying(2), f * Level.HIGH]

    assert [_operands(result.expression)[1] for result in results] == [2, 2, 3]
    assert all(type(_operands(result.expression)[1]) is int for result in results)


def test_a_float_subclass_reads_as_its_plain_float_beside_any_tracked_number() -> None:
    n = ConcolicInt.made(7, expression="n", sink=[])
    f = ConcolicFloat.made(0.5, expression="f", sink=[])

    results: list[Any] = [n < Gauge(2.5), n + Gauge(2.5), f < Gauge(2.5), f - Gauge(2.5)]

    assert [_operands(result.expression)[1] for result in results] == [2.5] * 4
    assert all(type(_operands(result.expression)[1]) is float for result in results)


def test_a_plain_bool_operand_stays_the_literal_it_is() -> None:
    n = ConcolicInt.made(7, expression="n", sink=[])

    result = n + True

    assert result.expression == ["+", "n", True]
    assert result.expression[2] is True


class Rev(int):
    """An int that defines its own reflected operations, which Python asks first on the right."""

    def __gt__(self, other: int) -> bool:
        return int.__lt__(self, other)

    def __lt__(self, other: int) -> bool:
        return int.__gt__(self, other)

    def __radd__(self, other: object) -> str:  # pyrefly: ignore[bad-override]
        return "Rev's own sum"

    def __rlshift__(self, other: object) -> str:  # pyrefly: ignore[bad-override]
        return "Rev's own shift"

    def __rpow__(self, other: object, modulus: object = None) -> str:
        return "Rev's own power"

    def __rfloordiv__(self, other: object) -> object:  # pyrefly: ignore[bad-override]
        # the int on the left, handed back as it came: tracked under pyct
        return other


class Shy(int):
    """An int whose own reflected sum hands the operation back."""

    def __radd__(self, other: object) -> object:  # pyrefly: ignore[bad-override]
        return NotImplemented


class Flag(IntFlag):
    A = 1


# each operation Python asks an int subclass on the right for first, when its type defines it
ASKED_FIRST: dict[str, tuple[Callable[[Any, Any], Any], str]] = {
    "greater": (lambda n, other: n > other, "__gt__"),
    "less": (lambda n, other: n < other, "__lt__"),
    "sum": (lambda n, other: n + other, "__add__"),
    "shift": (lambda n, other: n << other, "__lshift__"),
    "power": (lambda n, other: n**other, "__pow__"),
}


@pytest.mark.parametrize(("operation", "name"), ASKED_FIRST.values(), ids=ASKED_FIRST.keys())
def test_an_int_subclass_answers_its_reflected_operation_first_as_python_asks_it(
    operation: Callable[[Any, Any], Any], name: str
) -> None:
    sink: list[SinkItem] = []
    n = ConcolicInt.made(7, expression="n", sink=sink)

    result = operation(n, Rev(3))

    expected = operation(7, Rev(3))
    assert result == expected and type(result) is type(expected)
    # the answer is the subclass's own and plain, so the condition is lost and named
    assert sink == [Downgrade(name=name)]


def test_a_tracked_answer_from_an_int_subclass_is_no_downgrade() -> None:
    sink: list[SinkItem] = []
    n = ConcolicInt.made(7, expression="n", sink=sink)

    result = n // Rev(3)

    assert result is n
    assert sink == []
    assert result == 7 // Rev(3)


def test_an_int_flag_answers_with_its_own_flag_as_python_does() -> None:
    sink: list[SinkItem] = []
    n = ConcolicInt.made(7, expression="n", sink=sink)

    result = n | Flag.A

    expected = 7 | Flag.A
    assert result == expected and type(result) is type(expected)
    # IntFlag's own `|` runs `1 | n`, a downgrade of its own, and hands back a plain flag
    assert sink == [Downgrade(name="__ror__"), Downgrade(name="__or__")]


def test_an_int_subclass_that_hands_the_operation_back_leaves_it_to_the_int() -> None:
    sink: list[SinkItem] = []
    n = ConcolicInt.made(7, expression="n", sink=sink)

    result = n + Shy(2)

    assert sink == []
    assert result.expression == ["+", "n", 2]
    assert result == 7 + Shy(2)


def test_a_three_argument_power_asks_the_int_subclass_nothing() -> None:
    n = ConcolicInt.made(7, expression="n", sink=[])

    assert pow(n, Rev(2), 5) == pow(7, Rev(2), 5)


def test_a_reflected_call_on_the_tracked_int_asks_the_int_subclass_nothing() -> None:
    # Python has already asked the subclass on the left for `Rev(3) + n`, and int's own answered
    n = ConcolicInt.made(7, expression="n", sink=[])

    result = n.__radd__(Rev(3))

    assert result.expression == ["+", 3, "n"]


def test_a_tracked_bool_or_float_asks_an_int_subclass_nothing_as_python_does() -> None:
    # Rev subclasses neither bool nor float, so Python asks the left operand first
    sink: list[SinkItem] = []
    n = ConcolicInt.made(7, expression="n", sink=sink)
    f = ConcolicFloat.made(0.5, expression="f", sink=sink)

    # each on a bool and a float, so the same lambdas give plain Python's answers
    operations: list[Callable[[Any, Any], Any]] = [
        lambda b, _: b + Rev(3),
        lambda b, _: b > Rev(3),
        lambda _, g: g < Rev(3),
        lambda _, g: g + Rev(3),
    ]

    results = [operation(n > 0, f) for operation in operations]

    assert sink == []
    assert [result.expression for result in results] == [
        ["+", [">", "n", 0], 3],
        [">", [">", "n", 0], 3],
        ["<", "f", 3],
        ["+", "f", 3],
    ]
    assert results == [operation(True, 0.5) for operation in operations]


class Dial(float):
    """A float that defines its own reflected operations, which Python asks once int declines."""

    def __radd__(self, other: object) -> str:  # pyrefly: ignore[bad-override]
        return "Dial's own sum"

    def __rlshift__(self, other: object) -> str:
        return "Dial's own shift"

    def __rpow__(self, other: object, modulus: object = None) -> str:  # pyrefly: ignore[bad-override]
        return "Dial's own power"

    def __gt__(self, other: object) -> str:  # pyrefly: ignore[bad-override]
        return "Dial's own compare"

    def __rmul__(self, other: object) -> object:  # pyrefly: ignore[bad-override]
        # the int on the left, handed back as it came: tracked under pyct
        return other

    def __rsub__(self, other: object) -> object:  # pyrefly: ignore[bad-override]
        return NotImplemented


# each operation where int declines a float and Python asks a float subclass on the right
DIALED: dict[str, tuple[Callable[[Any, Any], Any], str]] = {
    "sum": (lambda n, other: n + other, "__add__"),
    "shift": (lambda n, other: n << other, "__lshift__"),
    "power": (lambda n, other: n**other, "__pow__"),
    "compare": (lambda n, other: n < other, "__lt__"),
}


@pytest.mark.parametrize(("operation", "name"), DIALED.values(), ids=DIALED.keys())
def test_a_float_subclass_answers_beside_a_tracked_int_as_python_asks_it(
    operation: Callable[[Any, Any], Any], name: str
) -> None:
    sink: list[SinkItem] = []
    n = ConcolicInt.made(7, expression="n", sink=sink)

    result = operation(n, Dial(2.0))

    assert result == operation(7, Dial(2.0))
    # the answer is the subclass's own and plain, so the condition is lost and named
    assert sink == [Downgrade(name=name)]


def test_a_tracked_answer_from_a_float_subclass_beside_a_tracked_int_is_no_downgrade() -> None:
    sink: list[SinkItem] = []
    n = ConcolicInt.made(7, expression="n", sink=sink)

    result = n * Dial(2.0)

    assert result is n
    assert sink == []
    assert int.__index__(result) == 7 * Dial(2.0)


def test_a_float_subclass_that_declines_beside_a_tracked_int_raises_as_python_does() -> None:
    sink: list[SinkItem] = []
    n = ConcolicInt.made(7, expression="n", sink=sink)

    with pytest.raises(TypeError):
        7 - Dial(2.0)
    with pytest.raises(TypeError):
        n - Dial(2.0)
    assert sink == []


class Coy(float):
    """A float whose own reflected power hands the operation back."""

    def __rpow__(self, other: object, modulus: object = None) -> object:  # pyrefly: ignore[bad-override]
        return NotImplemented


class Fwd(float):
    """A float that defines its own forward power alone."""

    def __pow__(self, other: object, modulus: object = None) -> object:  # pyrefly: ignore[bad-override]
        return NotImplemented


# the type name Python's message gives the int on the left, which pyct's names ConcolicInt
# (name-int-in-a-tracked-int-s-type-error)
PLAIN_INT_NAME = ("'int'", "'ConcolicInt'")


@pytest.mark.parametrize(
    "operation",
    [lambda n: n ** Coy(2.0), lambda n: pow(n, Dial(2.0), 5), lambda n: pow(n, Fwd(2.0), 5)],
    ids=["declined-power", "three-argument-power", "three-argument-forward-power"],
)
def test_a_power_a_float_subclass_does_not_answer_raises_as_python_does(
    operation: Callable[[Any], Any],
) -> None:
    sink: list[SinkItem] = []
    n = ConcolicInt.made(7, expression="n", sink=sink)

    with pytest.raises(TypeError) as plain:
        operation(7)
    with pytest.raises(TypeError) as raised:
        operation(n)

    # Python's own message, not float's, with only the left operand's type name apart
    assert str(raised.value) == str(plain.value).replace(*PLAIN_INT_NAME, 1)
    assert sink == []

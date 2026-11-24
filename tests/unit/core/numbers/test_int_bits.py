"""A tracked int's bit operations: `&`, `|`, `^` and `~`, and shifts by a constant."""

import json
import operator
import random
from collections.abc import Callable
from typing import Any
from unittest.mock import ANY

import pytest

from pyct.core.foundation.branch import Downgrade, SinkItem
from pyct.core.foundation.values import raised_by_target
from pyct.core.numbers.bools import ConcolicBool
from pyct.core.numbers.ints import ConcolicInt


def _anded(x: Any) -> Any:
    x &= 5
    return x


def _shifted(x: Any) -> Any:
    x <<= 2
    return x


# the call on a tracked x of 13, and the expression it builds, in Python's written order
TAUGHT: dict[str, tuple[Callable[[Any], object], list[object]]] = {
    "x & 6": (lambda x: x & 6, ["&", "x", 6]),
    "6 & x": (lambda x: 6 & x, ["&", 6, "x"]),
    "x | 6": (lambda x: x | 6, ["|", "x", 6]),
    "6 | x": (lambda x: 6 | x, ["|", 6, "x"]),
    "x ^ 6": (lambda x: x ^ 6, ["^", "x", 6]),
    "6 ^ x": (lambda x: 6 ^ x, ["^", 6, "x"]),
    "x & -8": (lambda x: x & -8, ["&", "x", -8]),
    "x & True": (lambda x: x & True, ["&", "x", True]),
    "~x": (lambda x: ~x, ["~", "x"]),
    "x << 3": (lambda x: x << 3, ["<<", "x", 3]),
    "x >> 2": (lambda x: x >> 2, [">>", "x", 2]),
    "x >> True": (lambda x: x >> True, [">>", "x", True]),
    "x << 4096": (lambda x: x << 4096, ["<<", "x", 4096]),
    "x &= 5": (_anded, ["&", "x", 5]),
    "x <<= 2": (_shifted, ["<<", "x", 2]),
}

OPERATORS: dict[str, Callable[[Any, Any], object]] = {
    "&": operator.and_,
    "|": operator.or_,
    "^": operator.xor,
    "<<": operator.lshift,
    ">>": operator.rshift,
}


@pytest.mark.parametrize(("call", "expression"), TAUGHT.values(), ids=list(TAUGHT))
def test_a_bit_operation_with_a_constant_carries_the_expression(
    call: Callable[[Any], object], expression: list[object]
) -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt.made(13, expression="x", sink=sink)

    result = call(x)

    assert isinstance(result, ConcolicInt)
    # operator.index reads the plain value: `==` on the result would fork into the sink
    assert operator.index(result) == call(13)
    # JSON tells the literal True from the int 1, where `==` on the lists does not
    assert json.dumps(result.expression) == json.dumps(expression)
    assert sink == []


@pytest.mark.parametrize("op", ["&", "|", "^"])
def test_two_tracked_ints_meet_in_a_bit_operation(op: str) -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt.made(12, expression="x", sink=sink)
    y = ConcolicInt.made(-7, expression="y", sink=sink)

    result = OPERATORS[op](x, y)

    assert isinstance(result, ConcolicInt)
    assert operator.index(result) == OPERATORS[op](12, -7)
    assert result.expression == [op, "x", "y"]
    assert sink == []


def test_a_tracked_bool_on_the_right_is_its_condition() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt.made(13, expression="x", sink=sink)
    b = ConcolicBool.made(True, expression=[">", "y", 0], sink=sink)

    result = x & b

    assert isinstance(result, ConcolicInt)
    assert operator.index(result) == 1
    assert result.expression == ["&", "x", [">", "y", 0]]


@pytest.mark.parametrize("op", list(OPERATORS))
def test_each_answer_is_pythons_on_random_ints(op: str) -> None:
    rng = random.Random(20261124)
    wide = [rng.randrange(-(2**80), 2**80) for _ in range(20)]
    small = [rng.randrange(-300, 300) for _ in range(20)]
    shift = op in ("<<", ">>")
    for value, other in zip(wide + small, small + wide, strict=True):
        count = abs(other) % 100 if shift else other
        x = ConcolicInt.made(value, expression="x", sink=[])

        result = OPERATORS[op](x, count)

        assert type(result) is ConcolicInt
        assert operator.index(result) == OPERATORS[op](value, count)
        if not shift:
            flipped = OPERATORS[op](other, x)
            assert type(flipped) is ConcolicInt
            assert operator.index(flipped) == OPERATORS[op](other, value)


def test_an_inverse_is_pythons_on_random_ints() -> None:
    rng = random.Random(7)
    for value in [rng.randrange(-(2**70), 2**70) for _ in range(20)] + [0, -1]:
        x = ConcolicInt.made(value, expression="x", sink=[])

        assert operator.index(~x) == ~value


# a shift Python reads a tracked or too large an amount for: int's own answer, and a downgrade
DOWNGRADED_SHIFTS: dict[str, tuple[Callable[[Any, Any], object], str]] = {
    "1 << n": (lambda x, n: 1 << n, "__rlshift__"),
    "256 >> n": (lambda x, n: 256 >> n, "__rrshift__"),
    "x << n": (lambda x, n: x << n, "__lshift__"),
    "x >> n": (lambda x, n: x >> n, "__rshift__"),
    "x << 4097": (lambda x, n: x << 4097, "__lshift__"),
    "x >> 4097": (lambda x, n: x >> 4097, "__rshift__"),
}


@pytest.mark.parametrize(("call", "name"), DOWNGRADED_SHIFTS.values(), ids=list(DOWNGRADED_SHIFTS))
def test_a_shift_by_a_tracked_or_large_amount_is_a_downgrade(
    call: Callable[[Any, Any], object], name: str
) -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt.made(13, expression="x", sink=sink)
    n = ConcolicInt.made(3, expression="n", sink=sink)

    result = call(x, n)

    assert result == call(13, 3)
    assert type(result) is int
    assert sink == [Downgrade(name=name, site=ANY)]


@pytest.mark.parametrize("op", ["<<", ">>"])
def test_a_negative_shift_count_raises_as_python_does(op: str) -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt.made(13, expression="x", sink=sink)

    with pytest.raises(ValueError) as raised:
        OPERATORS[op](x, -1)

    with pytest.raises(ValueError) as plain:
        OPERATORS[op](13, -1)
    assert str(raised.value) == str(plain.value)
    assert raised_by_target(raised.value)
    assert sink == []


@pytest.mark.parametrize("op", list(OPERATORS))
def test_a_float_beside_a_bit_operation_raises_as_python_does(op: str) -> None:
    x = ConcolicInt.made(13, expression="x", sink=[])

    with pytest.raises(TypeError) as raised:
        OPERATORS[op](x, 1.5)

    with pytest.raises(TypeError) as plain:
        OPERATORS[op](13, 1.5)
    assert str(raised.value) == str(plain.value)

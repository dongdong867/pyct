"""The names a number defines beside its dunders, on a tracked int, bool and float.

Each does one of four things, by what it hands back: the value itself, a constant, a
downgrade named by the method, or a classmethod that answers as the base type's own
(downgrades-class-body-taught-attributes-named).
"""

from collections.abc import Callable

import pytest

from pyct.core.bools import ConcolicBool
from pyct.core.branch import Downgrade, SinkItem
from pyct.core.floats import ConcolicFloat
from pyct.core.ints import ConcolicInt
from pyct.core.values import raised_by_target

# the names that hand back the value itself, on an int and on the bool that is an int
ITSELF: dict[str, Callable[[int], object]] = {
    "real": lambda x: x.real,
    "numerator": lambda x: x.numerator,
    "conjugate": lambda x: x.conjugate(),
    "as_integer_ratio": lambda x: x.as_integer_ratio()[0],
}

# the names that hand back a constant, reading nothing of the value
CONSTANTS: dict[str, Callable[[int], object]] = {
    "imag": lambda x: x.imag,
    "denominator": lambda x: x.denominator,
    "is_integer": lambda x: x.is_integer(),
}

# the names that hand back Python's answer, plain, with a downgrade named by the method
DOWNGRADED: dict[str, Callable[[int], object]] = {
    "bit_length": lambda x: x.bit_length(),
    "bit_count": lambda x: x.bit_count(),
    "to_bytes": lambda x: x.to_bytes(length=2, byteorder="big"),
}

# a classmethod reached through the value and through its class, each on its plain arguments
FROM_BYTES: dict[str, Callable[[int], object]] = {
    "x.from_bytes": lambda x: x.from_bytes(b"\x01\x00", "big"),
    "type(x).from_bytes": lambda x: type(x).from_bytes(b"\x01\x00", byteorder="big"),
}
FROMHEX: dict[str, Callable[[float], object]] = {
    "f.fromhex": lambda f: f.fromhex("0x1p2"),
    "type(f).fromhex": lambda f: type(f).fromhex("0x1p2"),
}


@pytest.mark.parametrize("read", ITSELF.values(), ids=list(ITSELF))
def test_an_int_hands_back_itself_and_records_nothing(read: Callable[[int], object]) -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    # the value itself, as `+x` is, so the condition is kept and no node is added
    assert read(x) is x
    assert sink == []


def test_an_ints_ratio_is_itself_over_a_plain_one() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    numerator, denominator = x.as_integer_ratio()

    assert numerator is x
    assert type(denominator) is int and denominator == 1
    assert sink == []


@pytest.mark.parametrize("read", CONSTANTS.values(), ids=list(CONSTANTS))
def test_an_int_reads_a_constant_plainly(read: Callable[[int], object]) -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    answer = read(x)

    assert answer == read(3)
    assert type(answer) is type(read(3))
    assert sink == []


@pytest.mark.parametrize(("name", "call"), DOWNGRADED.items(), ids=list(DOWNGRADED))
def test_an_int_downgrades_the_rest_by_name(name: str, call: Callable[[int], object]) -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    answer = call(x)

    assert answer == call(3)
    assert type(answer) is type(call(3))
    assert sink == [Downgrade(name=name)]


def test_an_identity_refuses_what_ints_own_refuses() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    with pytest.raises(TypeError) as plain:
        (3).conjugate(1)  # pyrefly: ignore[bad-argument-count]
    with pytest.raises(TypeError) as raised:
        x.conjugate(1)  # pyrefly: ignore[bad-argument-count]

    assert str(raised.value) == str(plain.value)
    assert raised_by_target(raised.value)
    assert sink == []


@pytest.mark.parametrize("build", FROM_BYTES.values(), ids=list(FROM_BYTES))
def test_from_bytes_through_a_tracked_int_is_ints_own(build: Callable[[int], object]) -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    answer = build(x)

    # it reads the class and never the value, so it is int's plain answer
    assert type(answer) is int and answer == 256
    assert sink == []


def test_from_bytes_through_a_tracked_bool_is_bools_own() -> None:
    sink: list[SinkItem] = []
    b = ConcolicBool(True, expression=[">", "x", 0], sink=sink)

    # plain Python builds a bool here too: `True.from_bytes(b"\x01\x00", "big")` is True
    assert b.from_bytes(b"\x01\x00", "big") is True.from_bytes(b"\x01\x00", "big")
    assert sink == []


def test_a_classmethod_raises_what_the_base_type_raises() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    with pytest.raises(ValueError) as plain:
        int.from_bytes(b"\x01", "middle")  # pyrefly: ignore[bad-argument-type]
    with pytest.raises(ValueError) as raised:
        x.from_bytes(b"\x01", "middle")  # pyrefly: ignore[bad-argument-type]

    assert str(raised.value) == str(plain.value)
    assert raised_by_target(raised.value)
    assert sink == []


@pytest.mark.parametrize("read", ITSELF.values(), ids=list(ITSELF))
def test_a_bool_hands_back_the_int_it_is(read: Callable[[int], object]) -> None:
    sink: list[SinkItem] = []
    b = ConcolicBool(True, expression=[">", "x", 0], sink=sink)

    answer = read(b)

    # the int 1, with the bool's condition, as `+b` is
    assert type(answer) is ConcolicInt and answer.expression == [">", "x", 0]
    assert int.__index__(answer) == 1
    assert sink == []


@pytest.mark.parametrize("read", CONSTANTS.values(), ids=list(CONSTANTS))
def test_a_bool_reads_ints_constants_plainly(read: Callable[[int], object]) -> None:
    sink: list[SinkItem] = []
    b = ConcolicBool(True, expression=[">", "x", 0], sink=sink)

    answer = read(b)

    assert answer == read(True)
    assert type(answer) is type(read(True))
    assert sink == []


@pytest.mark.parametrize(("name", "call"), DOWNGRADED.items(), ids=list(DOWNGRADED))
def test_a_bool_downgrades_what_an_int_does(name: str, call: Callable[[int], object]) -> None:
    sink: list[SinkItem] = []
    b = ConcolicBool(True, expression=[">", "x", 0], sink=sink)

    assert call(b) == call(True)
    assert sink == [Downgrade(name=name)]


@pytest.mark.parametrize("read", [lambda f: f.real, lambda f: f.conjugate()], ids=["real", "conj"])
def test_a_float_hands_back_itself(read: Callable[[float], object]) -> None:
    sink: list[SinkItem] = []
    f = ConcolicFloat(0.5, expression="f", sink=sink)

    assert read(f) is f
    assert sink == []


def test_a_floats_imag_is_a_plain_zero() -> None:
    sink: list[SinkItem] = []
    f = ConcolicFloat(0.5, expression="f", sink=sink)

    assert type(f.imag) is float and f.imag == 0.0
    assert sink == []


@pytest.mark.parametrize("build", FROMHEX.values(), ids=list(FROMHEX))
def test_fromhex_through_a_tracked_float_is_floats_own(build: Callable[[float], object]) -> None:
    sink: list[SinkItem] = []
    f = ConcolicFloat(0.5, expression="f", sink=sink)

    answer = build(f)

    assert type(answer) is float and answer == 4.0
    assert sink == []

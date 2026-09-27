"""The names a number defines beside its dunders, on a tracked int, bool and float.

Each does one of four things, by what it hands back: the value itself, a constant, a
downgrade named by the method, or a classmethod that answers as the base type's own
(downgrades-class-body-taught-attributes-named).
"""

import types
from collections.abc import Callable
from unittest.mock import ANY

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


# a call an identity refuses, on a plain value of each kind; the tracked value refuses it alike
REFUSED_IDENTITIES: dict[str, tuple[float, Callable[[object], object]]] = {
    "int conjugate(1)": (3, lambda x: x.conjugate(1)),  # pyrefly: ignore[missing-attribute]
    "int as_integer_ratio(1)": (3, lambda x: x.as_integer_ratio(1)),  # pyrefly: ignore[missing-attribute]
    "float conjugate(1)": (0.5, lambda f: f.conjugate(1)),  # pyrefly: ignore[missing-attribute]
}


def _set_real(value: object) -> None:
    value.real = 1  # pyrefly: ignore[missing-attribute]


def _delete_real(value: object) -> None:
    del value.real  # pyrefly: ignore[missing-attribute]


# writing an attribute that hands back the value itself, which Python refuses
WRITES: dict[str, Callable[[object], None]] = {"set real": _set_real, "del real": _delete_real}


def _tracked(value: float, sink: list[SinkItem]) -> object:
    """The tracked value of a plain int, bool or float, as `x` or the compare `x > 0`."""
    if isinstance(value, bool):
        return ConcolicBool(value, expression=[">", "x", 0], sink=sink)
    if isinstance(value, float):
        return ConcolicFloat(value, expression="x", sink=sink)
    return ConcolicInt(value, expression="x", sink=sink)


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
    assert sink == [Downgrade(name=name, site=ANY)]


@pytest.mark.parametrize(
    ("value", "refused"), REFUSED_IDENTITIES.values(), ids=list(REFUSED_IDENTITIES)
)
def test_an_identity_refuses_what_the_base_types_own_refuses(
    value: float, refused: Callable[[object], object]
) -> None:
    sink: list[SinkItem] = []
    tracked = _tracked(value, sink)

    with pytest.raises(TypeError) as plain:
        refused(value)
    with pytest.raises(TypeError) as raised:
        refused(tracked)

    assert str(raised.value) == str(plain.value)
    assert raised_by_target(raised.value)
    assert sink == []


@pytest.mark.parametrize("value", [3, True, 0.5], ids=["int", "bool", "float"])
@pytest.mark.parametrize("change", WRITES.values(), ids=list(WRITES))
def test_writing_an_attribute_raises_what_python_raises(
    value: float, change: Callable[[object], None]
) -> None:
    sink: list[SinkItem] = []
    tracked = _tracked(value, sink)

    with pytest.raises(AttributeError) as plain:
        change(value)
    with pytest.raises(AttributeError) as raised:
        change(tracked)

    assert str(raised.value) == str(plain.value)
    assert raised_by_target(raised.value)
    assert sink == []


@pytest.mark.parametrize(
    ("cls", "base"),
    [(ConcolicInt, int), (ConcolicBool, int), (ConcolicFloat, float)],
    ids=["int", "bool", "float"],
)
def test_every_classmethod_of_the_base_type_is_named_in_the_class_body(
    cls: type, base: type
) -> None:
    # the derivation reads only methods called on a value, so a classmethod a newer Python
    # adds would build the concolic class from the value alone and crash the target; on every
    # Python pyct runs on, each one the base type defines is named in the class body
    classmethods = {
        name
        for name, member in vars(base).items()
        if isinstance(member, types.ClassMethodDescriptorType)
    }

    assert classmethods
    assert classmethods <= set(vars(cls))


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
    assert sink == [Downgrade(name=name, site=ANY)]


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

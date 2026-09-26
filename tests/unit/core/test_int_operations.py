import copy
import dataclasses
import math
import operator
from collections.abc import Callable

import pytest

from pyct.core import values
from pyct.core.branch import Downgrade, SinkItem
from pyct.core.ints import ConcolicInt
from pyct.core.values import raised_by_target

# one call per untaught operation, a spread of them wide enough to stand for the whole list
DOWNGRADED_CALLS: dict[str, Callable[[int], object]] = {
    "__truediv__": lambda x: x / 2,
    "__lshift__": lambda x: x << 1,
    "__rshift__": lambda x: x >> 1,
    "__and__": lambda x: x & 1,
    "__or__": lambda x: x | 1,
    "__xor__": lambda x: x ^ 1,
    "__invert__": lambda x: ~x,
    "__float__": float,
}

# the taught arithmetic: the call, and the expression it builds; each keeps Python's written order
TAUGHT_ARITHMETIC: dict[str, tuple[Callable[[int], object], list[object]]] = {
    "x + 1": (lambda x: x + 1, ["+", "x", 1]),
    "1 + x": (lambda x: 1 + x, ["+", 1, "x"]),
    "x - 1": (lambda x: x - 1, ["-", "x", 1]),
    "10 - x": (lambda x: 10 - x, ["-", 10, "x"]),
    "x * 2": (lambda x: x * 2, ["*", "x", 2]),
    "2 * x": (lambda x: 2 * x, ["*", 2, "x"]),
    "-x": (lambda x: -x, ["-", "x"]),
    "abs(x)": (abs, ["abs", "x"]),
    "x ** 2": (lambda x: x**2, ["**", "x", 2]),
    "x ** 0": (lambda x: x**0, ["**", "x", 0]),
}

# an operation that changes nothing about an int: each hands the value itself back
IDENTITIES: dict[str, Callable[[ConcolicInt], object]] = {
    "+x": lambda x: +x,
    "round(x)": round,
    "round(x, 1)": lambda x: round(x, 1),
    "x.__index__()": lambda x: x.__index__(),
    "math.trunc(x)": math.trunc,
    "math.floor(x)": math.floor,
    "math.ceil(x)": math.ceil,
}


@dataclasses.dataclass
class Holder:
    """A dataclass the target keeps an int in."""

    value: int


# copy, deepcopy and asdict, each on data holding a tracked int or a compare's value: the call,
# and the value it hands back
COPIES: dict[str, Callable[[int], object]] = {
    "copy.copy(v)": copy.copy,
    "copy.deepcopy(v)": copy.deepcopy,
    "copy.deepcopy({'value': v})": lambda v: copy.deepcopy({"value": v})["value"],
    "dataclasses.asdict(Holder(v))": lambda v: dataclasses.asdict(Holder(v))["value"],
}

# a power the solver cannot take: each is int's own answer and a `__pow__` downgrade
DOWNGRADED_POWERS: dict[str, Callable[[int], object]] = {
    "negative exponent": lambda x: x**-1,
    "bool exponent": lambda x: x**True,
    "with a modulus": lambda x: pow(x, 2, 5),
    "past cvc5's bound": lambda x: x**67_108_864,
}

# int's plain members, the ones pyct wraps in nothing: each call is int's own answer. The four
# attributes are read and never called; `from_bytes` is a classmethod and has its own test
PLAIN_INT_MEMBERS: dict[str, Callable[[int], object]] = {
    "as_integer_ratio": lambda x: x.as_integer_ratio(),
    "bit_count": lambda x: x.bit_count(),
    "bit_length": lambda x: x.bit_length(),
    "conjugate": lambda x: x.conjugate(),
    "denominator": lambda x: x.denominator,
    "imag": lambda x: x.imag,
    "is_integer": lambda x: x.is_integer(),
    "numerator": lambda x: x.numerator,
    "real": lambda x: x.real,
    "to_bytes": lambda x: x.to_bytes(1),
}


def test_a_concolic_int_is_a_real_int() -> None:
    x = ConcolicInt(3, expression="x", sink=[])

    assert isinstance(x, int)
    assert x == 3
    assert x.expression == "x"


def test_an_untaught_operation_returns_a_plain_int() -> None:
    x = ConcolicInt(3, expression="x", sink=[])

    assert type(x >> 1) is int


@pytest.mark.parametrize(("name", "call"), DOWNGRADED_CALLS.items(), ids=list(DOWNGRADED_CALLS))
def test_an_untaught_operation_returns_a_plain_value_and_records_its_name(
    name: str, call: Callable[[int], object]
) -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    result = call(x)

    assert result == call(3)
    assert not isinstance(result, ConcolicInt)
    assert sink == [Downgrade(name=name)]


@pytest.mark.parametrize(
    ("call", "expression"), TAUGHT_ARITHMETIC.values(), ids=list(TAUGHT_ARITHMETIC)
)
def test_a_taught_operation_answers_with_an_int_that_carries_the_expression(
    call: Callable[[int], object], expression: list[object]
) -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    result = call(x)

    assert isinstance(result, ConcolicInt)
    # operator.index reads the plain value: `==` on the result would fork into the sink
    assert operator.index(result) == call(3)
    assert result.expression == expression
    assert result.sink is sink
    # arithmetic tests nothing for truth and loses nothing, so the sink stays empty
    assert sink == []


def test_an_operation_on_two_concolic_ints_names_both() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)
    y = ConcolicInt(4, expression="y", sink=sink)

    result = x * y

    assert isinstance(result, ConcolicInt)
    assert operator.index(result) == 12
    assert result.expression == ["*", "x", "y"]


def test_arithmetic_nests_the_way_it_was_written() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(0, expression="x", sink=sink)

    result = (x + 1) * 2 - 3

    assert isinstance(result, ConcolicInt)
    assert result.expression == ["-", ["*", ["+", "x", 1], 2], 3]


def test_a_bool_operand_is_pythons_own_arithmetic() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    # a bool is an int, but `x + True` is not an operation the solver has a leaf for;
    # the same rule as the compares, so the value is plain and nothing is recorded
    result = x + True

    assert result == 4
    assert not isinstance(result, ConcolicInt)
    assert sink == []


@pytest.mark.parametrize("call", DOWNGRADED_POWERS.values(), ids=list(DOWNGRADED_POWERS))
def test_a_power_the_solver_cannot_take_is_a_downgrade(call: Callable[[int], object]) -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(1, expression="x", sink=sink)

    result = call(x)

    assert result == call(1)
    assert not isinstance(result, ConcolicInt)
    assert sink == [Downgrade(name="__pow__")]


def test_a_float_exponent_is_floats_own_power() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(4, expression="x", sink=sink)

    # int itself answers NotImplemented to a float exponent and float takes over, so the
    # condition is lost on the other side and nothing here records it
    assert x**0.5 == 2.0
    assert sink == []


def test_a_symbolic_exponent_is_a_downgrade() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(2, expression="x", sink=sink)
    y = ConcolicInt(3, expression="y", sink=sink)

    assert x**y == 8
    assert 2**x == 4

    # cvc5 takes a constant exponent only, so both spellings stay int's own
    assert sink == [Downgrade(name="__pow__"), Downgrade(name="__rpow__")]


@pytest.mark.parametrize("call", IDENTITIES.values(), ids=list(IDENTITIES))
def test_an_identity_operation_hands_the_value_itself_back(
    call: Callable[[ConcolicInt], object],
) -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    assert call(x) is x
    assert sink == []


@pytest.mark.parametrize("call", COPIES.values(), ids=list(COPIES))
def test_a_copy_of_a_concolic_int_is_the_value_itself(call: Callable[[int], object]) -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    # copy hands a plain int back as it is, because an int cannot change; a tracked one comes
    # back the same way, its expression and sink with it, so nothing is lost
    assert call(x) is x
    assert sink == []


@pytest.mark.parametrize("call", COPIES.values(), ids=list(COPIES))
def test_a_copy_of_a_compares_value_is_the_value_itself(call: Callable[[int], object]) -> None:
    sink: list[SinkItem] = []
    big = ConcolicInt(3, expression="x", sink=sink) > 10

    # the same holds for the value a compare hands back, so testing the copy records the fork
    assert call(big) is big
    assert sink == []


def test_int_of_a_concolic_int_is_a_downgrade() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    # Python copies whatever __int__ hands back into a plain int, so the condition cannot
    # survive int(x) from inside the class: int-conversion-stays-a-downgrade
    result = int(x)

    assert type(result) is int
    assert sink == [Downgrade(name="__int__")]


def test_rounding_to_a_power_of_ten_is_a_downgrade() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(1234, expression="x", sink=sink)

    assert round(x, -2) == 1200
    assert sink == [Downgrade(name="__round__")]


def test_a_concolic_int_hashes_like_an_int_and_records_nothing() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    assert hash(x) == hash(3)
    assert {x: "small"}[x] == "small"

    assert sink == []


def test_reading_a_concolic_int_back_records_nothing() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    # repr is the debugger's path, not the target's
    assert repr(x) == "3"

    assert sink == []


def test_the_object_plumbing_on_a_concolic_int_records_nothing() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    # pickling and the interpreter's own reads are not the target's path
    assert x.__getnewargs__() == (3,)
    assert x.__sizeof__() == (3).__sizeof__()
    assert x.__getattribute__("real") == 3

    assert sink == []


@pytest.mark.parametrize("call", PLAIN_INT_MEMBERS.values(), ids=list(PLAIN_INT_MEMBERS))
def test_a_plain_int_member_gives_ints_own_answer_and_records_nothing(
    call: Callable[[int], object],
) -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    # each hands back a plain value, so `==` against int's own answer forks nothing
    assert call(x) == call(3)
    assert sink == []


def test_int_from_bytes_on_a_concolic_int_records_nothing() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    # from_bytes is int's classmethod, so no tracked value reaches it as a receiver. Bound to
    # the subclass it asks ConcolicInt for a value with no expression and no sink, and int's
    # own TypeError comes back; whatever it answers, it records nothing
    with pytest.raises(TypeError):
        x.from_bytes(b"\x03")

    assert sink == []


def test_turning_a_concolic_int_into_text_records_a_downgrade() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    assert str(x) == "3"
    assert f"{x:d}" == "3"

    assert sink == [Downgrade(name="__str__"), Downgrade(name="__format__")]


def test_an_empty_format_goes_through_str_and_records_both() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    assert f"{x}" == "3"

    # int's own __format__ formats an empty spec by asking str, so the f-string loses it twice
    assert sink == [Downgrade(name="__str__"), Downgrade(name="__format__")]


def test_using_a_concolic_int_as_an_index_records_nothing() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    assert list(range(x)) == [0, 1, 2]

    # an int subclass is already an index to CPython, which never asks __index__ for one
    assert sink == []


def test_asking_a_concolic_int_for_its_index_is_the_value_itself() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    assert x.__index__() is x

    assert sink == []


def test_an_operation_that_raises_records_nothing() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    with pytest.raises(ZeroDivisionError):
        _ = x // 0

    # nothing was lost: the raise is the target's own
    assert sink == []


def test_a_raise_out_of_ints_own_operation_is_marked_as_the_targets() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    with pytest.raises(ZeroDivisionError) as raised:
        _ = x // 0

    # pyct only ran int's own divide, so the raise that came out of it is the target's
    assert raised_by_target(raised.value)


def test_a_raise_pyct_made_itself_carries_no_mark() -> None:
    assert not raised_by_target(ValueError("pyct's own"))


def test_a_raise_that_is_not_the_operations_carries_no_mark() -> None:
    def interrupted() -> int:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt) as raised:
        values.own(interrupted)

    # a deadline and a keyboard interrupt land inside int's own operation too, and are not its raise
    assert not raised_by_target(raised.value)


def test_a_downgrade_hands_keywords_to_the_base_types_own_method() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)
    to_bytes = values.downgraded(int, "to_bytes")

    # no int downgrade takes a keyword today; to_bytes does, so the factory is built on it here
    assert to_bytes(x, length=2, byteorder="big") == b"\x00\x03"
    assert sink == [Downgrade(name="to_bytes")]


def test_a_keyword_named_like_pycts_own_parameter_is_ints_own_raise() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    with pytest.raises(TypeError) as plain:
        (3).__format__(operation="d")  # pyrefly: ignore[bad-argument-count, unexpected-keyword]
    with pytest.raises(TypeError) as raised:
        x.__format__(operation="d")  # pyrefly: ignore[bad-argument-count, unexpected-keyword]

    # operation is the name pyct gives the base type's method; int refuses the keyword itself,
    # in its own words, the way it does on a plain value
    assert str(raised.value) == str(plain.value)
    assert raised_by_target(raised.value)
    assert sink == []


def test_an_operation_the_other_type_answers_records_nothing() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    # int cannot add a float, so float's reflected add answers and int's own never did
    assert x + 1.5 == 4.5

    assert sink == []

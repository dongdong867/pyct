import copy
import dataclasses
import json
import math
import operator
import sys
from collections.abc import Callable

import pytest

from pyct.core import values
from pyct.core.branch import Downgrade, SinkItem
from pyct.core.ints import ConcolicInt
from pyct.core.strs import ConcolicStr
from pyct.core.values import raised_by_target

# one call per untaught operation, a spread of them wide enough to stand for the whole list
DOWNGRADED_CALLS: dict[str, Callable[[int], object]] = {
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
    "x ** True": (lambda x: x**True, ["**", "x", True]),
}

# an operation that changes nothing about an int: each hands the value itself back
IDENTITIES: dict[str, Callable[[ConcolicInt], object]] = {
    "+x": lambda x: +x,
    "round(x)": round,
    "round(x, 1)": lambda x: round(x, 1),
    "round(x, True)": lambda x: round(x, True),
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
    "with a modulus": lambda x: pow(x, 2, 5),
    "past cvc5's bound": lambda x: x**67_108_864,
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
    # JSON tells the literal True from the int 1, where `==` on the lists does not
    assert json.dumps(result.expression) == json.dumps(expression)
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


def test_a_bool_operand_is_the_int_1_or_0() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    # a bool is the int 1 or 0, as Python has it, so `x + True` is a node on the literal
    result = x + True

    assert isinstance(result, ConcolicInt)
    assert json.dumps(result.expression) == json.dumps(["+", "x", True])
    assert int.__int__(result) == 4
    assert sink == []


@pytest.mark.parametrize("call", DOWNGRADED_POWERS.values(), ids=list(DOWNGRADED_POWERS))
def test_a_power_the_solver_cannot_take_is_a_downgrade(call: Callable[[int], object]) -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(1, expression="x", sink=sink)

    result = call(x)

    assert result == call(1)
    assert not isinstance(result, ConcolicInt)
    assert sink == [Downgrade(name="__pow__")]


def test_a_float_exponent_is_floats_own_power_and_a_downgrade() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(4, expression="x", sink=sink)

    # no solver operation gives CPython's pow to the last bit, so float's own answers and the
    # loss is named, where int's own NotImplemented would hand it to float silently
    result = x**0.5

    assert type(result) is float
    assert result == 2.0
    assert sink == [Downgrade(name="__pow__")]


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

    # `__getnewargs__` and the interpreter's own reads are not the target's path
    assert x.__getnewargs__() == (3,)
    assert x.__sizeof__() == (3).__sizeof__()
    assert x.__getattribute__("imag") == 0

    assert sink == []


# each way Python turns an int alone into text: it hands the tracked str `__str__` or
# `__format__` gives back on whole
TEXT_ALONE: dict[str, Callable[[int], object]] = {
    "str(x)": str,
    "format(x)": format,
    'format(x, "")': lambda x: format(x, ""),
    'f"{x}"': lambda x: f"{x}",
    '"{}".format(x)': lambda x: "{}".format(x),  # noqa: UP032
    '"%s" % x': lambda x: "%s" % x,  # noqa: UP031
    "map(str, [x])": lambda x: next(map(str, [x])),
}


@pytest.mark.parametrize("value", [3, -42, 0])
@pytest.mark.parametrize("call", TEXT_ALONE.values(), ids=list(TEXT_ALONE))
def test_an_int_alone_turned_into_text_is_its_tracked_text(
    call: Callable[[int], object], value: int
) -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(value, expression="x", sink=sink)

    text = call(x)

    assert isinstance(text, ConcolicStr)
    assert (str.__str__(text), text.expression, text.sink) == (call(value), ["str", "x"], sink)
    assert sink == []


def test_text_joined_around_an_int_is_plain_and_records_nothing() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(7, expression="x", sink=sink)

    # Python joins the pieces without calling any method of the tracked str
    text = f"n={x}"

    assert (text, type(text)) == ("n=7", str)
    assert sink == []


# the `%` forms that write the text themselves: every integer conversion, with any flag, width or
# precision, reads the number without calling any of its methods; `%r` and `%a` read the kept
# `__repr__`; and a width or a precision on `%s` pads or cuts the text `__str__` hands back into
# a new plain str
INTEGER_CONVERSIONS = ["%d", "%i", "%u", "%o", "%x", "%X", "%c"]
PERCENT_PLAIN = [
    *INTEGER_CONVERSIONS,
    "%5d",
    "%-5i",
    "%+d",
    "% d",
    "%05u",
    "%#o",
    "%#x",
    "%#X",
    "%.3d",
    "%3c",
    "%r",
    "%a",
    "%5s",
    "%.1s",
    "n=%s",
]
# the float conversions, which convert the number through its `__float__`
FLOAT_CONVERSIONS = ["%e", "%E", "%f", "%F", "%g", "%G", "%.2f", "%10.3e"]


def _tracked_values(sink: list[SinkItem]) -> list[tuple[object, int | bool]]:
    """A tracked int and a tracked bool, beside the plain value each is."""
    x = ConcolicInt(65, expression="x", sink=sink)
    return [(x, 65), (x > 0, True)]


@pytest.mark.parametrize("form", PERCENT_PLAIN)
def test_a_percent_form_that_writes_the_text_itself_is_plain_and_silent(form: str) -> None:
    sink: list[SinkItem] = []

    for tracked, plain in _tracked_values(sink):
        text = form % tracked

        assert (text, type(text)) == (form % plain, str)
    assert sink == []


@pytest.mark.parametrize("form", FLOAT_CONVERSIONS)
def test_a_float_percent_conversion_is_a_float_downgrade(form: str) -> None:
    sink: list[SinkItem] = []

    for tracked, plain in _tracked_values(sink):
        text = form % tracked

        assert (text, type(text)) == (form % plain, str)
    assert sink == [Downgrade(name="__float__"), Downgrade(name="__float__")]


@pytest.mark.parametrize("spec", ["d", "05d", "x", ">4", ","])
def test_a_format_spec_is_a_downgrade_named_format(spec: str) -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(1234, expression="x", sink=sink)

    text = format(x, spec)

    assert (text, type(text)) == (format(1234, spec), str)
    assert sink == [Downgrade(name="__format__")]


def test_text_past_pythons_digit_limit_raises_as_the_targets() -> None:
    sink: list[SinkItem] = []
    huge = 10 ** (sys.get_int_max_str_digits() + 1)
    x = ConcolicInt(huge, expression="x", sink=sink)

    with pytest.raises(ValueError) as raised:
        str(x)

    with pytest.raises(ValueError) as plain:
        str(huge)
    assert str(raised.value) == str(plain.value)
    assert raised_by_target(raised.value)
    assert sink == []


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

    # to_bytes is a derived downgrade that takes keywords
    assert x.to_bytes(length=2, byteorder="big") == b"\x00\x03"
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


def test_an_operation_the_other_type_answers_is_named_as_a_downgrade() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    class Measured(float):
        def __radd__(self, other: object) -> str:  # pyrefly: ignore[bad-override]
            return "measured"

    # a float of the target's own that adds itself otherwise than float is asked, as Python
    # asks it for a plain int, and int's own never answered
    assert x + Measured(1.5) == 3 + Measured(1.5)

    # its answer is plain, so x's condition is lost there and the operation is named
    assert sink == [Downgrade(name="__add__")]

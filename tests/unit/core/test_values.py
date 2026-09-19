import math
import operator
from collections.abc import Callable

import pytest

from pyct.core import values
from pyct.core.branch import Branch, Downgrade, SinkItem, Site
from pyct.core.values import ConcolicBool, ConcolicInt, raised_by_target

# one call per untaught operation, a spread of them wide enough to stand for the whole list
DOWNGRADED_CALLS: dict[str, Callable[[int], object]] = {
    "__truediv__": lambda x: x / 2,
    "__floordiv__": lambda x: x // 2,
    "__mod__": lambda x: x % 2,
    "__divmod__": lambda x: divmod(x, 2),
    "__lshift__": lambda x: x << 1,
    "__rshift__": lambda x: x >> 1,
    "__and__": lambda x: x & 1,
    "__or__": lambda x: x | 1,
    "__xor__": lambda x: x ^ 1,
    "__invert__": lambda x: ~x,
    "__float__": float,
}

# the six taught comparisons: the call, and the answer int's own gives for x = 3
TAUGHT_COMPARES: dict[str, tuple[Callable[[int], object], bool]] = {
    "<": (lambda x: x < 3, False),
    "<=": (lambda x: x <= 3, True),
    ">": (lambda x: x > 3, False),
    ">=": (lambda x: x >= 3, True),
    "==": (lambda x: x == 3, True),
    "!=": (lambda x: x != 3, False),
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

# a power the solver cannot take: each is int's own answer and a `__pow__` downgrade
DOWNGRADED_POWERS: dict[str, Callable[[int], object]] = {
    "negative exponent": lambda x: x**-1,
    "bool exponent": lambda x: x**True,
    "with a modulus": lambda x: pow(x, 2, 5),
    "past cvc5's bound": lambda x: x**67_108_864,
}

# a probe whose text is fixed here, so the line and column of the fork are exact
PROBE = "def probe(v):\n    if v:\n        return 'yes'\n    return 'no'\n"

# a probe that asks for the truth of a value the other two ways Python spells it
NOT_AND_BOOL = (
    "def probe(x):\n"
    "    n = 0\n"
    "    if not x:\n"
    "        n += 1\n"
    "    if bool(x):\n"
    "        n += 1\n"
    "    return n\n"
)

# a probe that tests the same value twice, so the order the sink holds is visible
TWO_CHECKS = (
    "def probe(x):\n"
    "    n = 0\n"
    "    if x < 10:\n"
    "        n += 1\n"
    "    if x < 100:\n"
    "        n += 1\n"
    "    return n\n"
)


def _probe(source: str = PROBE) -> Callable[..., object]:
    namespace: dict[str, object] = {}
    exec(compile(source, "<probe>", "exec"), namespace)
    probe = namespace["probe"]
    assert callable(probe)
    return probe


def test_a_concolic_int_is_a_real_int() -> None:
    x = ConcolicInt(3, expression="x", sink=[])

    assert isinstance(x, int)
    assert x == 3
    assert x.expression == "x"


def test_an_untaught_operation_returns_a_plain_int() -> None:
    x = ConcolicInt(3, expression="x", sink=[])

    assert type(x >> 1) is int


@pytest.mark.parametrize(("op", "case"), TAUGHT_COMPARES.items(), ids=list(TAUGHT_COMPARES))
def test_a_taught_compare_builds_its_expression_and_records_nothing(
    op: str, case: tuple[Callable[[int], object], bool]
) -> None:
    call, answer = case
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    result = call(x)

    assert isinstance(result, ConcolicBool)
    assert result.expression == [op, "x", 3]
    # int.__bool__, not bool(result): bool() would record the fork this test is not about
    assert int.__bool__(result) is answer
    assert sink == []


def test_a_taught_compare_against_a_truth_value_is_pythons_own() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)
    y = ConcolicInt(3, expression="y", sink=sink)

    # a bool and a compare's value stand for a truth value, not a number, so `>=` against
    # either is int's own: a plain bool, and no leaf that drops the compare behind it
    assert (x >= True) is True
    assert (x >= (y < 5)) is True

    assert sink == []


def test_less_than_builds_the_expression_and_records_nothing() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    result = x < 10

    assert result.expression == ["<", "x", 10]
    assert result == True  # noqa: E712 - the value, not the truth test
    assert sink == []


def test_less_than_takes_the_other_concolics_expression() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)
    y = ConcolicInt(10, expression="y", sink=sink)

    result = x < y

    assert result.expression == ["<", "x", "y"]


def test_less_than_a_non_int_is_pythons_own_compare() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    # a float is not an int, so the compare is float's and nothing symbolic is recorded
    assert (x < 3.5) is True
    assert sink == []


def test_less_than_a_bool_is_pythons_own_compare() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    assert (x < True) is False
    assert sink == []


def test_equal_to_a_non_int_is_pythons_own_answer() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    # both sides answer NotImplemented; Python settles `==` by identity instead of raising
    assert (x == None) is False  # noqa: E711 - the target's spelling
    assert (x != "a") is True
    assert sink == []


def test_less_than_a_compares_value_is_pythons_own_compare() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(0, expression="x", sink=sink)
    y = ConcolicInt(3, expression="y", sink=sink)

    # a compare's value stands for a truth value, not a number, so `<` against it is
    # int's own: a plain bool, not a leaf that drops y's compare for its concrete 1
    assert (x < (y < 5)) is True
    assert sink == []


def test_less_than_carries_the_concrete_result() -> None:
    x = ConcolicInt(50, expression="x", sink=[])

    assert (x < 10) == False  # noqa: E712 - the value, not the truth test


def test_a_compare_adds_up_like_a_bool() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    assert sum([x < 10, x < 100]) == 2

    # sum adds, it never tests for truth
    assert sink == []


def test_a_compare_equals_the_bool_it_stands_for() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    assert (x < 10) == True  # noqa: E712 - comparing to True is what the target may do
    assert (x < 100) == True  # noqa: E712 - same

    # `==` against an int never tests for truth
    assert sink == []


def test_a_compare_reads_back_as_a_bool() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    assert repr(x < 10) == "True"
    assert repr(x < 100) == "True"

    assert sink == []


def test_the_truth_test_records_the_fork_where_it_happens() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    # the compare happens here, the truth test inside the probe; the fork is the probe's
    assert _probe()(x < 10) == "yes"

    assert sink == [
        Branch(expression=["<", "x", 10], taken=True, site=Site(file="<probe>", line=2, col=7))
    ]


def test_a_reflected_compare_records_the_same_fork() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    # int has no way to compare against a subclass, so Python asks x first: `x < 10`
    assert _probe()(10 > x) == "yes"  # noqa: SIM300 - the reflected form is the point

    assert sink == [
        Branch(expression=["<", "x", 10], taken=True, site=Site(file="<probe>", line=2, col=7))
    ]


def test_the_truth_test_records_the_side_it_took() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(50, expression="x", sink=sink)

    assert _probe()(x < 10) == "no"

    assert [item.taken for item in sink if isinstance(item, Branch)] == [False]


def test_two_truth_tests_reach_the_sink_in_the_order_they_ran() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(5, expression="x", sink=sink)

    assert _probe(TWO_CHECKS)(x) == 2

    assert sink == [
        Branch(expression=["<", "x", 10], taken=True, site=Site(file="<probe>", line=3, col=7)),
        Branch(expression=["<", "x", 100], taken=True, site=Site(file="<probe>", line=5, col=7)),
    ]


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


def test_equality_forks_where_it_is_tested_for_truth() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    assert _probe()(x == 3) == "yes"

    assert sink == [
        Branch(expression=["==", "x", 3], taken=True, site=Site(file="<probe>", line=2, col=7))
    ]


def test_a_truth_test_on_a_concolic_int_records_the_fork() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    # the int itself is the condition, so the fork is the probe's `if`, like a compare's
    assert _probe()(x) == "yes"

    assert sink == [
        Branch(expression=["!=", "x", 0], taken=True, site=Site(file="<probe>", line=2, col=7))
    ]


def test_a_truth_test_on_zero_records_the_side_it_took() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(0, expression="x", sink=sink)

    assert _probe(NOT_AND_BOOL)(x) == 1

    # `not` and `bool()` ask __bool__ the way `if` does, so each records its own fork.
    # The column is the instruction's own: `not x` converts x, so it points at the x.
    assert sink == [
        Branch(expression=["!=", "x", 0], taken=False, site=Site(file="<probe>", line=3, col=11)),
        Branch(expression=["!=", "x", 0], taken=False, site=Site(file="<probe>", line=5, col=7)),
    ]


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
        values._own(interrupted)

    # a deadline and a keyboard interrupt land inside int's own operation too, and are not its raise
    assert not raised_by_target(raised.value)


def test_an_operation_the_other_type_answers_records_nothing() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    # int cannot add a float, so float's reflected add answers and int's own never did
    assert x + 1.5 == 4.5

    assert sink == []


def test_a_reflected_compare_records_the_compare_python_ran() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    # Python swaps the operands: `10 < x` asks x first, as `x.__gt__(10)`
    assert _probe()(10 < x) == "no"  # noqa: SIM300 - the reflected form is the point

    assert sink == [
        Branch(expression=[">", "x", 10], taken=False, site=Site(file="<probe>", line=2, col=7))
    ]


def test_downgrades_and_a_fork_reach_the_sink_in_the_order_they_ran() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    assert x >> 1 == 1
    assert str(x) == "3"
    assert _probe()(x < 10) == "yes"

    assert sink == [
        Downgrade(name="__rshift__"),
        Downgrade(name="__str__"),
        Branch(expression=["<", "x", 10], taken=True, site=Site(file="<probe>", line=2, col=7)),
    ]


def test_every_int_operation_is_taught_kept_or_downgraded() -> None:
    # a name none of the three sets holds runs as int's own with no downgrade, silently
    taught = {"__lt__", "__le__", "__gt__", "__ge__", "__eq__", "__ne__", "__bool__"}
    taught |= {"__add__", "__radd__", "__sub__", "__rsub__", "__mul__", "__rmul__"}
    taught |= {"__neg__", "__abs__", "__pow__"}
    taught |= {"__pos__", "__index__", "__round__", "__trunc__", "__floor__", "__ceil__"}
    kept = {"__new__", "__getattribute__", "__hash__", "__repr__", "__sizeof__", "__getnewargs__"}
    downgraded = {
        name
        for name, member in vars(ConcolicInt).items()
        if name.startswith("__") and callable(member) and name not in taught | kept
    }
    # int inherits __str__ from object and still counts it: print(x) drops the condition
    ints_own = {
        name for name in vars(int) if name.startswith("__") and callable(getattr(int, name))
    }

    assert downgraded == (ints_own | {"__str__"}) - taught - kept


def test_every_operation_that_reaches_ints_own_goes_through_the_helper() -> None:
    # a call into int written without the helper leaves its raise blamed on pyct, silently
    written_here = {
        name: code
        for name, member in vars(ConcolicInt).items()
        if name.startswith("__")
        and (code := getattr(member, "__code__", None)) is not None
        and code.co_filename == values.__file__
    }
    # a downgrade closure reaches int through the helper itself, so handing it the call counts;
    # what makes one is being built by _downgraded, not what it is called
    reaches_int = {"_own"} | {
        name
        for name, value in vars(values).items()
        if getattr(value, "__qualname__", "").startswith("_downgraded.")
    }
    without_the_helper = {
        name for name, code in written_here.items() if not reaches_int & set(code.co_names)
    }

    # these hand the value itself back and never call int, so they have nothing to guard
    assert without_the_helper == {"__pos__", "__index__", "__trunc__", "__floor__", "__ceil__"}

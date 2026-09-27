"""A tracked bool used as a number: the int 1 or 0, with the condition it stands for."""

import json
import math
from collections.abc import Callable

import pytest

from pyct.core.bools import ConcolicBool
from pyct.core.branch import Branch, Downgrade, Expression, SinkItem, Site
from pyct.core.ints import ConcolicInt
from pyct.core.strs import ConcolicStr
from pyct.core.values import raised_by_target

# the condition every test here tests: `x > 0`, true for x = 1
ABOVE: Expression = [">", "x", 0]
BELOW: Expression = [">", "y", 0]

# a bool's arithmetic, the call on a true and a false condition, and the node it builds.
# Each keeps Python's written order, and answers what the ints 1 and 0 answer
ARITHMETIC: dict[str, tuple[Callable[[int, int], object], list[object]]] = {
    "b + c": (lambda b, c: b + c, ["+", ABOVE, BELOW]),
    "b - c": (lambda b, c: b - c, ["-", ABOVE, BELOW]),
    "b * c": (lambda b, c: b * c, ["*", ABOVE, BELOW]),
    "b + 5": (lambda b, c: b + 5, ["+", ABOVE, 5]),
    "5 - b": (lambda b, c: 5 - b, ["-", 5, ABOVE]),
    "3 * c": (lambda b, c: 3 * c, ["*", 3, BELOW]),
    "-b": (lambda b, c: -b, ["-", ABOVE]),
    "abs(b)": (lambda b, c: abs(b), ["abs", ABOVE]),
    "b ** 2": (lambda b, c: b**2, ["**", ABOVE, 2]),
    "b // 1": (lambda b, c: b // 1, ["//", ABOVE, 1]),
    "c % 2": (lambda b, c: c % 2, ["%", BELOW, 2]),
}

# a bool's compares: the call on a true and a false condition, and the node it builds
COMPARES: dict[str, tuple[Callable[[int, int], object], list[object]]] = {
    "b == c": (lambda b, c: b == c, ["==", ABOVE, BELOW]),
    "b != c": (lambda b, c: b != c, ["!=", ABOVE, BELOW]),
    "b < 1": (lambda b, c: b < 1, ["<", ABOVE, 1]),
    "b <= c": (lambda b, c: b <= c, ["<=", ABOVE, BELOW]),
    "b > True": (lambda b, c: b > True, [">", ABOVE, True]),
    "b >= 0": (lambda b, c: b >= 0, [">=", ABOVE, 0]),
}

# `&`, `|` and `^` between two bools: the call on a true and a false condition, and the node
LOGICAL: dict[str, tuple[Callable[[int, int], object], list[object]]] = {
    "b & c": (lambda b, c: b & c, ["&", ABOVE, BELOW]),
    "b | c": (lambda b, c: b | c, ["|", ABOVE, BELOW]),
    "b ^ c": (lambda b, c: b ^ c, ["^", ABOVE, BELOW]),
    "b & True": (lambda b, c: b & True, ["&", ABOVE, True]),
    "c | False": (lambda b, c: c | False, ["|", BELOW, False]),
}

# an operation that leaves a bool's value as it is, as the int it is: `+True` is 1 in Python
AS_THE_INT: dict[str, Callable[[int], object]] = {
    "+b": lambda b: +b,
    "round(b)": round,
    "round(b, 2)": lambda b: round(b, 2),
    "round(b, False)": lambda b: round(b, False),
    "math.trunc(b)": math.trunc,
    "math.floor(b)": math.floor,
    "math.ceil(b)": math.ceil,
    "b.__index__()": lambda b: b.__index__(),
}

# an operation a bool has not taught: the call, and the name the line gives the loss
UNTAUGHT: dict[str, tuple[Callable[[int], object], str]] = {
    "~b": (lambda b: ~b, "__invert__"),
    "b << 1": (lambda b: b << 1, "__lshift__"),
    "b & 3": (lambda b: b & 3, "__and__"),
    "3 & b": (lambda b: 3 & b, "__rand__"),
    "int(b)": (int, "__int__"),
    "float(b)": (float, "__float__"),
    "b / 2": (lambda b: b / 2, "__truediv__"),
    "round(b, -1)": (lambda b: round(b, -1), "__round__"),
}

# probes whose text is fixed here, so the line and column of a fork are exact
REFLECTED = "def probe(b):\n    return 7 // b\n"
DIVIDE = "def probe(a, b):\n    return a % b\n"
DIVMOD = "def probe(a, b):\n    return divmod(a, b)\n"
# divmod with the bool on either side: the probe's arguments, the two nodes, the values, and
# whether the bool is the divisor, the one side that forks
BOOL_DIVMODS: dict[
    str, tuple[Callable[[object], tuple[object, ...]], list[object], tuple[int, int], bool]
] = {
    "divmod(b, 2)": (lambda b: (b, 2), [["//", ABOVE, 2], ["%", ABOVE, 2]], (0, 1), False),
    "divmod(10, b)": (lambda b: (10, b), [["//", 10, ABOVE], ["%", 10, ABOVE]], (10, 0), True),
}
DIVISION_SITE = Site(file="<probe>", line=2, col=11)


def _probe(source: str) -> Callable[..., object]:
    namespace: dict[str, object] = {}
    exec(compile(source, "<probe>", "exec"), namespace)
    probe = namespace["probe"]
    assert callable(probe)
    return probe


def _conditions(sink: list[SinkItem]) -> tuple[ConcolicBool, ConcolicBool]:
    """`x > 0` on x = 1 and `y > 0` on y = 0: one true and one false tracked bool."""
    x = ConcolicInt(1, expression="x", sink=sink)
    y = ConcolicInt(0, expression="y", sink=sink)
    return x > 0, y > 0


@pytest.mark.parametrize(("call", "node"), ARITHMETIC.values(), ids=list(ARITHMETIC))
def test_a_bools_arithmetic_is_the_ints_with_its_condition(
    call: Callable[[int, int], object], node: list[object]
) -> None:
    sink: list[SinkItem] = []

    result = call(*_conditions(sink))

    assert isinstance(result, ConcolicInt)
    # JSON tells the literal True from the int 1, where `==` on the lists does not
    assert json.dumps(result.expression) == json.dumps(node)
    # int.__int__, not int(result): int() would record the loss this test is not about
    assert int.__int__(result) == call(1, 0)
    # arithmetic never tests for truth, and a taught operation loses nothing
    assert sink == []


@pytest.mark.parametrize(("call", "node"), COMPARES.values(), ids=list(COMPARES))
def test_a_bools_compare_is_a_tracked_bool(
    call: Callable[[int, int], object], node: list[object]
) -> None:
    sink: list[SinkItem] = []

    result = call(*_conditions(sink))

    assert isinstance(result, ConcolicBool)
    assert json.dumps(result.expression) == json.dumps(node)
    # int.__bool__, not bool(result): bool() would record the fork this test is not about
    assert int.__bool__(result) is call(True, False)
    assert sink == []


@pytest.mark.parametrize(("call", "node"), LOGICAL.values(), ids=list(LOGICAL))
def test_and_or_and_xor_between_two_bools_answer_a_tracked_bool(
    call: Callable[[int, int], object], node: list[object]
) -> None:
    sink: list[SinkItem] = []

    result = call(*_conditions(sink))

    assert isinstance(result, ConcolicBool)
    # a plain bool is the literal True or False, which render reads as a Bool, never the int 1
    assert json.dumps(result.expression) == json.dumps(node)
    assert int.__bool__(result) is call(True, False)
    assert sink == []


def test_a_sum_of_bools_counts_the_conditions() -> None:
    sink: list[SinkItem] = []
    above, below = _conditions(sink)

    result = sum([above, below])

    # sum starts from 0 and adds each in turn, as Python does
    assert isinstance(result, ConcolicInt)
    assert result.expression == ["+", ["+", 0, ABOVE], BELOW]
    assert int.__int__(result) == 1
    assert sink == []


def test_a_bool_meets_a_str_as_python_makes_it() -> None:
    sink: list[SinkItem] = []
    above, _ = _conditions(sink)

    # `==` with a str is a plain constant, and an order with one raises in Python
    assert (above == "yes") is False
    assert (above != "yes") is True
    with pytest.raises(TypeError):
        _ = above < "a"

    assert sink == []


@pytest.mark.parametrize("call", AS_THE_INT.values(), ids=list(AS_THE_INT))
def test_an_identity_operation_answers_the_int_with_the_same_condition(
    call: Callable[[int], object],
) -> None:
    sink: list[SinkItem] = []
    above, _ = _conditions(sink)

    result = call(above)

    # the same condition, no node added, but the int 1 as Python answers it, so it reads 1
    assert isinstance(result, ConcolicInt)
    assert result.expression == ABOVE
    assert repr(result) == repr(call(True)) == "1"
    assert sink == []


@pytest.mark.parametrize(("call", "name"), UNTAUGHT.values(), ids=list(UNTAUGHT))
def test_an_untaught_operation_is_a_downgrade(call: Callable[[int], object], name: str) -> None:
    sink: list[SinkItem] = []
    above, _ = _conditions(sink)

    result = call(above)

    # the loss is recorded by name, and the value is int's own answer on the 1 the bool is
    assert result == call(1)
    assert not isinstance(result, ConcolicInt | ConcolicBool)
    assert sink == [Downgrade(name=name)]


def test_a_bool_reads_as_true_or_false() -> None:
    sink: list[SinkItem] = []
    above, below = _conditions(sink)

    assert (repr(above), repr(below)) == ("True", "False")
    assert sink == []

    # the text is a tracked str carrying the condition, and testing it records nothing yet
    texts = [str(above), f"{below}", format(above), "%s" % below]  # noqa: UP031
    tracked = [text for text in texts if isinstance(text, ConcolicStr)]
    assert [(str.__str__(text), text.expression) for text in tracked] == [
        ("True", ["str", [">", "x", 0]]),
        ("False", ["str", [">", "y", 0]]),
        ("True", ["str", [">", "x", 0]]),
        ("False", ["str", [">", "y", 0]]),
    ]
    assert sink == []


def test_a_bools_format_spec_is_a_downgrade() -> None:
    sink: list[SinkItem] = []
    above, _ = _conditions(sink)

    assert f"{above:>5}" == f"{True:>5}"
    assert sink == [Downgrade(name="__format__")]


def test_a_bool_formats_with_a_spec_as_python_formats_a_bool() -> None:
    above, _ = _conditions([])

    assert f"{above:d}|{above:>5}|{above:.1f}" == f"{True:d}|{True:>5}|{True:.1f}"


def test_a_bad_format_spec_raises_as_the_targets() -> None:
    sink: list[SinkItem] = []
    above, _ = _conditions(sink)

    with pytest.raises(ValueError) as raised:
        format(above, "s")

    with pytest.raises(ValueError) as plain:
        format(True, "s")
    # the format runs on the bool this is, so the sentence names bool, as plain Python's does
    assert str(raised.value) == str(plain.value)
    assert raised_by_target(raised.value)
    assert sink == []


def test_a_reflected_division_by_a_bool_forks_on_its_own_condition() -> None:
    sink: list[SinkItem] = []
    above, _ = _conditions(sink)

    result = _probe(REFLECTED)(above)

    # the zero fork is the bool's condition, as `if` would test it, not `!= 0` around it
    assert sink == [Branch(expression=ABOVE, taken=True, site=DIVISION_SITE)]
    assert isinstance(result, ConcolicInt)
    assert result.expression == ["//", 7, ABOVE]
    assert int.__int__(result) == 7


def test_an_int_divided_by_a_bool_forks_on_its_condition() -> None:
    sink: list[SinkItem] = []
    above, _ = _conditions(sink)
    x = ConcolicInt(5, expression="x", sink=sink)

    result = _probe(DIVMOD)(x, above)

    assert sink == [Branch(expression=ABOVE, taken=True, site=DIVISION_SITE)]
    assert isinstance(result, tuple)
    assert [part.expression for part in result] == [["//", "x", ABOVE], ["%", "x", ABOVE]]


@pytest.mark.parametrize(
    ("arguments", "nodes", "answer", "divisor"), BOOL_DIVMODS.values(), ids=list(BOOL_DIVMODS)
)
def test_divmod_with_a_bool_divides_the_int_it_is(
    arguments: Callable[[object], tuple[object, ...]],
    nodes: list[object],
    answer: tuple[int, int],
    divisor: bool,
) -> None:
    sink: list[SinkItem] = []
    above, _ = _conditions(sink)

    result = _probe(DIVMOD)(*arguments(above))

    assert isinstance(result, tuple)
    assert json.dumps([part.expression for part in result]) == json.dumps(nodes)
    assert tuple(int.__int__(part) for part in result) == answer
    # only a tracked divisor forks, and a bool forks on its own condition
    fork = Branch(expression=ABOVE, taken=True, site=DIVISION_SITE)
    assert sink == ([fork] if divisor else [])


def test_a_division_by_a_false_bool_raises_with_its_fork_recorded() -> None:
    sink: list[SinkItem] = []
    _, below = _conditions(sink)

    with pytest.raises(ZeroDivisionError) as raised:
        _probe(DIVIDE)(10, below)

    assert sink == [Branch(expression=BELOW, taken=False, site=DIVISION_SITE)]
    assert raised_by_target(raised.value)

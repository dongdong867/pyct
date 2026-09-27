import json
import operator
from collections.abc import Callable

import pytest

from pyct.core.branch import Branch, SinkItem, Site
from pyct.core.ints import ConcolicInt
from pyct.core.values import raised_by_target

# a division by a constant: the call, and the node it builds. Nothing here can be zero,
# so none of them forks
CONSTANT_DIVISORS: dict[str, tuple[Callable[[int], object], list[object]]] = {
    "x // 2": (lambda x: x // 2, ["//", "x", 2]),
    "x % 2": (lambda x: x % 2, ["%", "x", 2]),
    "x // -2": (lambda x: x // -2, ["//", "x", -2]),
    "x % -3": (lambda x: x % -3, ["%", "x", -3]),
}

# a division whose divisor is symbolic: the call, and the node it builds. Each keeps
# Python's written order, so the reflected forms read as the target wrote them
SYMBOLIC_DIVISORS: dict[str, tuple[Callable[[int, int], object], list[object]]] = {
    "x // y": (lambda x, y: x // y, ["//", "x", "y"]),
    "x % y": (lambda x, y: x % y, ["%", "x", "y"]),
    "7 // y": (lambda x, y: 7 // y, ["//", 7, "y"]),
    "7 % y": (lambda x, y: 7 % y, ["%", 7, "y"]),
}

# Python floors toward minus infinity and its remainder takes the divisor's sign; what a
# target sees is int's own answer, on every combination of signs
SIGNED_PAIRS = [(7, 2), (7, -2), (-7, 2), (-7, -2), (9, -2), (8, -2), (2, -3)]

# a plain bool divisor is the int 1 or 0: the call, and the node it builds on the literal
BOOL_DIVISORS: dict[str, tuple[Callable[[int], object], list[object]]] = {
    "x // True": (lambda x: x // True, ["//", "x", True]),
    "x % True": (lambda x: x % True, ["%", "x", True]),
}

# probes whose text is fixed here, so the line and column of the zero fork are exact
DIVIDE = "def probe(a, b):\n    return a // b\n"
REFLECTED = "def probe(b):\n    return 7 // b\n"
DIVMOD = "def probe(a, b):\n    return divmod(a, b)\n"
REFLECTED_DIVMOD = "def probe(b):\n    return divmod(7, b)\n"

# every probe divides on its second line, at the column its expression starts
DIVISION_SITE = Site(file="<probe>", line=2, col=11)


def _probe(source: str) -> Callable[..., object]:
    namespace: dict[str, object] = {}
    exec(compile(source, "<probe>", "exec"), namespace)
    probe = namespace["probe"]
    assert callable(probe)
    return probe


def _branches(sink: list[SinkItem]) -> list[Branch]:
    """The forks a sink holds, so a count means forks rather than items."""
    return [item for item in sink if isinstance(item, Branch)]


@pytest.mark.parametrize(
    ("call", "expression"), CONSTANT_DIVISORS.values(), ids=list(CONSTANT_DIVISORS)
)
def test_a_division_by_a_constant_builds_its_node_and_forks_nothing(
    call: Callable[[int], object], expression: list[object]
) -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(7, expression="x", sink=sink)

    result = call(x)

    assert isinstance(result, ConcolicInt)
    # int.__int__ reads the plain value: `==` on the result would fork into the sink
    assert int.__int__(result) == call(7)
    assert result.expression == expression
    # a constant divisor has no side to flip, so the division records nothing at all
    assert sink == []


@pytest.mark.parametrize(
    ("call", "expression"), SYMBOLIC_DIVISORS.values(), ids=list(SYMBOLIC_DIVISORS)
)
def test_a_division_by_a_symbolic_divisor_builds_its_node_and_forks_on_the_divisor(
    call: Callable[[int, int], object], expression: list[object]
) -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(7, expression="x", sink=sink)
    y = ConcolicInt(2, expression="y", sink=sink)

    result = call(x, y)

    assert isinstance(result, ConcolicInt)
    assert operator.index(result) == call(7, 2)
    assert result.expression == expression
    assert [(item.expression, item.taken) for item in _branches(sink)] == [(["!=", "y", 0], True)]


def test_the_zero_fork_is_recorded_where_the_division_ran() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(7, expression="x", sink=sink)
    y = ConcolicInt(2, expression="y", sink=sink)

    _probe(DIVIDE)(x, y)

    # the division happens inside the probe, so the fork is the probe's line, not this one
    assert sink == [Branch(expression=["!=", "y", 0], taken=True, site=DIVISION_SITE)]


def test_the_reflected_form_records_the_same_fork() -> None:
    sink: list[SinkItem] = []
    y = ConcolicInt(2, expression="y", sink=sink)

    # `7 // y` runs int's reflected divide on y, and y is still the divisor
    _probe(REFLECTED)(y)

    assert sink == [Branch(expression=["!=", "y", 0], taken=True, site=DIVISION_SITE)]


def test_divmod_divides_once_and_forks_once() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(7, expression="x", sink=sink)
    y = ConcolicInt(2, expression="y", sink=sink)

    _probe(DIVMOD)(x, y)

    # one call divides once, where `x // y` and `x % y` written out would fork twice
    assert sink == [Branch(expression=["!=", "y", 0], taken=True, site=DIVISION_SITE)]


def test_the_reflected_divmod_forks_once_too() -> None:
    sink: list[SinkItem] = []
    y = ConcolicInt(2, expression="y", sink=sink)

    _probe(REFLECTED_DIVMOD)(y)

    assert sink == [Branch(expression=["!=", "y", 0], taken=True, site=DIVISION_SITE)]


def test_divmod_hands_back_a_quotient_and_a_remainder_that_carry_their_own_nodes() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(7, expression="x", sink=sink)

    quotient, remainder = divmod(x, 5)

    assert isinstance(quotient, ConcolicInt) and isinstance(remainder, ConcolicInt)
    assert quotient.expression == ["//", "x", 5]
    assert remainder.expression == ["%", "x", 5]


def test_the_reflected_divmod_keeps_the_order_the_target_wrote() -> None:
    sink: list[SinkItem] = []
    y = ConcolicInt(5, expression="y", sink=sink)

    quotient, remainder = divmod(7, y)

    assert isinstance(quotient, ConcolicInt) and isinstance(remainder, ConcolicInt)
    assert quotient.expression == ["//", 7, "y"]
    assert remainder.expression == ["%", 7, "y"]


@pytest.mark.parametrize(("a", "b"), SIGNED_PAIRS, ids=[f"{a} by {b}" for a, b in SIGNED_PAIRS])
def test_a_division_hands_back_pythons_own_value(a: int, b: int) -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(a, expression="x", sink=sink)
    y = ConcolicInt(b, expression="y", sink=sink)
    quotient, remainder = divmod(x, b)

    assert operator.index(quotient) == a // b
    assert operator.index(remainder) == a % b
    assert operator.index(x // b) == a // b
    assert operator.index(x % b) == a % b
    assert operator.index(a // y) == a // b
    assert operator.index(a % y) == a % b


@pytest.mark.parametrize(("call", "node"), BOOL_DIVISORS.values(), ids=list(BOOL_DIVISORS))
def test_a_plain_bool_divisor_divides_by_1_or_0(
    call: Callable[[int], object], node: list[object]
) -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(7, expression="x", sink=sink)

    result = call(x)

    # a plain divisor has nothing to flip, so no zero fork is recorded
    assert isinstance(result, ConcolicInt)
    # JSON tells the literal True from the int 1, where `==` on the lists does not
    assert json.dumps(result.expression) == json.dumps(node)
    assert int.__int__(result) == call(7)
    assert sink == []


def test_a_plain_bool_divisor_divides_by_1_or_0_in_divmod() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(7, expression="x", sink=sink)

    quotient, remainder = divmod(x, True)

    assert json.dumps([quotient.expression, remainder.expression]) == json.dumps(
        [["//", "x", True], ["%", "x", True]]
    )
    assert (int.__int__(quotient), int.__int__(remainder)) == (7, 0)
    assert sink == []


# a divisor int does not take: the call, forward and reflected. Each is the other type's
# business, and here both sides refuse it
REFUSED_DIVISORS: dict[str, Callable[[int], object]] = {
    "x // 'a'": lambda x: x // "a",  # pyrefly: ignore[unsupported-operation]
    "[] % x": lambda x: [] % x,  # pyrefly: ignore[unsupported-operation]
    "divmod(x, 'a')": lambda x: divmod(x, "a"),  # pyrefly: ignore[no-matching-overload]
    "divmod('a', x)": lambda x: divmod("a", x),  # pyrefly: ignore[no-matching-overload]
}


@pytest.mark.parametrize("call", REFUSED_DIVISORS.values(), ids=list(REFUSED_DIVISORS))
def test_a_divisor_int_does_not_take_is_left_to_python(call: Callable[[int], object]) -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(7, expression="x", sink=sink)

    # NotImplemented from both sides, so Python raises, and nothing forks before it does
    with pytest.raises(TypeError):
        call(x)
    assert sink == []


def test_a_division_by_zero_raises_with_the_fork_it_died_on_already_recorded() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(7, expression="x", sink=sink)
    y = ConcolicInt(0, expression="y", sink=sink)

    with pytest.raises(ZeroDivisionError) as raised:
        _probe(DIVIDE)(x, y)

    # the fork goes in before int divides, so the crashing input still carries the side it took
    assert sink == [Branch(expression=["!=", "y", 0], taken=False, site=DIVISION_SITE)]
    # pyct only ran int's own divide, so the raise that came out of it is the target's
    assert raised_by_target(raised.value)

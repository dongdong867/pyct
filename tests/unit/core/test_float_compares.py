import math
from collections.abc import Callable
from unittest.mock import ANY

import pytest

from pyct.core.bools import ConcolicBool
from pyct.core.branch import Branch, Downgrade, SinkItem, Site
from pyct.core.floats import ConcolicFloat
from pyct.core.ints import ConcolicInt

# the six taught comparisons: the call, and the answer float's own gives for x = 2.5
TAUGHT_COMPARES: dict[str, tuple[Callable[[float], object], bool]] = {
    "<": (lambda x: x < 2.5, False),
    "<=": (lambda x: x <= 2.5, True),
    ">": (lambda x: x > 2.5, False),
    ">=": (lambda x: x >= 2.5, True),
    "==": (lambda x: x == 2.5, True),
    "!=": (lambda x: x != 2.5, False),
}

# an operand float answers but pyct does not encode, and the dunder its compare runs: an int
# meets a float in follow-floats-that-meet-ints, a bool in follow-booleans
NOT_ENCODED: dict[str, tuple[Callable[[float], object], str]] = {
    "x < 3": (lambda x: x < 3, "__lt__"),
    "x == True": (lambda x: x == True, "__eq__"),  # noqa: E712 - the target's spelling
    "3 < x": (lambda x: 3 < x, "__gt__"),  # noqa: SIM300 - the reflected form is the point
    "x >= n": (lambda x: x >= ConcolicInt(2, expression="n", sink=[]), "__ge__"),
}

# a probe whose text is fixed here, so the line and column of the fork are exact
PROBE = "def probe(v):\n    if v:\n        return 'yes'\n    return 'no'\n"
PROBE_SITE = Site(file="<probe>", line=2, col=7)


def _probe(source: str = PROBE) -> Callable[..., object]:
    namespace: dict[str, object] = {}
    exec(compile(source, "<probe>", "exec"), namespace)
    probe = namespace["probe"]
    assert callable(probe)
    return probe


@pytest.mark.parametrize(("op", "case"), TAUGHT_COMPARES.items(), ids=list(TAUGHT_COMPARES))
def test_a_taught_compare_builds_its_expression_and_records_nothing(
    op: str, case: tuple[Callable[[float], object], bool]
) -> None:
    call, answer = case
    sink: list[SinkItem] = []
    x = ConcolicFloat(2.5, expression="x", sink=sink)

    result = call(x)

    assert isinstance(result, ConcolicBool)
    assert result.expression == [op, "x", 2.5]
    # int.__bool__, not bool(result): bool() would record the fork this test is not about
    assert int.__bool__(result) is answer
    assert sink == []


def test_a_compare_against_a_tracked_float_takes_its_expression() -> None:
    sink: list[SinkItem] = []
    x = ConcolicFloat(1.5, expression="x", sink=sink)
    y = ConcolicFloat(2.5, expression="y", sink=sink)

    result = x < y

    assert isinstance(result, ConcolicBool)
    assert result.expression == ["<", "x", "y"]
    assert sink == []


def test_a_float_on_the_left_is_compared_the_other_way_round() -> None:
    x = ConcolicFloat(3.0, expression="x", sink=[])

    # Python asks the float subclass on the right first, with the operator mirrored
    result = 2.5 < x  # noqa: SIM300 - the reflected form is the point

    assert isinstance(result, ConcolicBool)
    assert result.expression == [">", "x", 2.5]


def test_a_float_of_the_targets_own_is_a_plain_float_leaf() -> None:
    class Celsius(float):
        def __repr__(self) -> str:
            return f"{float(self)}°C"

    x = ConcolicFloat(3.0, expression="x", sink=[])

    result = x < Celsius(4.0)

    assert isinstance(result, ConcolicBool)
    assert isinstance(result.expression, list)
    assert result.expression == ["<", "x", 4.0]
    assert type(result.expression[2]) is float


@pytest.mark.parametrize(("call", "name"), NOT_ENCODED.values(), ids=list(NOT_ENCODED))
def test_an_operand_float_answers_but_pyct_does_not_encode_is_a_downgrade(
    call: Callable[[float], object], name: str
) -> None:
    sink: list[SinkItem] = []
    x = ConcolicFloat(2.5, expression="x", sink=sink)

    result = call(x)

    # float's own answer, where NotImplemented would hand the compare to int, which has none
    assert type(result) is bool
    assert result is call(2.5)
    assert sink == [Downgrade(name=name, site=ANY)]


def test_equal_to_a_str_is_pythons_own_constant() -> None:
    sink: list[SinkItem] = []
    x = ConcolicFloat(1.5, expression="x", sink=sink)

    # both sides answer NotImplemented; Python settles `==` by identity instead of raising
    assert (x == "a") is False
    assert (x != "a") is True
    assert sink == []


def test_an_order_against_a_str_raises_pythons_own_type_error() -> None:
    sink: list[SinkItem] = []
    x = ConcolicFloat(1.5, expression="x", sink=sink)

    with pytest.raises(TypeError, match="'<' not supported"):
        _ = x < "a"
    assert sink == []


def test_the_truth_test_records_the_fork_where_it_happens() -> None:
    sink: list[SinkItem] = []
    x = ConcolicFloat(1.5, expression="x", sink=sink)

    assert _probe()(x) == "yes"

    assert sink == [Branch(expression=["!=", "x", 0.0], taken=True, site=PROBE_SITE)]


@pytest.mark.parametrize(
    ("value", "truth"), [(0.0, False), (-0.0, False), (math.nan, True), (-math.inf, True)]
)
def test_zero_is_the_one_value_on_the_other_side_of_the_truth_test(
    value: float, truth: bool
) -> None:
    sink: list[SinkItem] = []
    x = ConcolicFloat(value, expression="x", sink=sink)

    assert _probe()(x) == ("yes" if truth else "no")
    assert sink == [Branch(expression=["!=", "x", 0.0], taken=truth, site=PROBE_SITE)]


class Gauge(float):
    """A float subclass of a library's own, as numpy.float64 is, with a compare of its own."""

    def __gt__(self, other: object) -> object:  # pyrefly: ignore[bad-override]
        return "gauge >"

    def __eq__(self, other: object) -> object:  # pyrefly: ignore[bad-override]
        return "gauge =="

    __hash__ = float.__hash__


def test_a_float_subclass_with_its_own_reflected_compare_answers_first() -> None:
    sink: list[SinkItem] = []
    x = ConcolicFloat(2.5, expression="x", sink=sink)

    # `x < g` asks `g.__gt__` first, as it would with a plain 2.5 on the left
    assert (2.5 < Gauge(1.0)) == "gauge >"  # noqa: SIM300 - the order is the point
    assert (x < Gauge(1.0)) == "gauge >"
    assert (x == Gauge(1.0)) == "gauge =="
    assert sink == []

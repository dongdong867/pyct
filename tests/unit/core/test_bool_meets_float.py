"""A bool meeting a float: the double 1.0 or 0.0, as Python's numbers meet."""

from collections.abc import Callable

import pytest

from pyct.core.bools import ConcolicBool
from pyct.core.branch import Branch, Expression, SinkItem
from pyct.core.floats import ConcolicFloat

ABOVE: Expression = [">", "x", 0]

# a tracked bool, true, and a tracked float, 2.0: the call, and the node it builds. Each keeps
# Python's written order, and answers what Python answers for True and 2.0
MIXED: dict[str, tuple[Callable[[int, float], object], list[object]]] = {
    "b + 0.5": (lambda b, f: b + 0.5, ["+", ABOVE, 0.5]),
    "b * 2.5": (lambda b, f: b * 2.5, ["*", ABOVE, 2.5]),
    "b - f": (lambda b, f: b - f, ["-", ABOVE, "f"]),
    "b / 2": (lambda b, f: b / 2, ["/", ABOVE, 2]),
    "b / 0.5": (lambda b, f: b / 0.5, ["/", ABOVE, 0.5]),
    "b // 0.5": (lambda b, f: b // 0.5, ["//", ABOVE, 0.5]),
    "b % f": (lambda b, f: b % f, ["%", ABOVE, "f"]),
    "f + True": (lambda b, f: f + True, ["+", "f", True]),
    "f * b": (lambda b, f: f * b, ["*", "f", ABOVE]),
    "True + f": (lambda b, f: True + f, ["+", True, "f"]),
    "f / True": (lambda b, f: f / True, ["/", "f", True]),
    "f - False": (lambda b, f: f - False, ["-", "f", False]),
}

# the compares, the node each builds, and Python's answer for True and 2.0
COMPARED: dict[str, tuple[Callable[[int, float], object], list[object]]] = {
    "b < 2.5": (lambda b, f: b < 2.5, ["<", ABOVE, 2.5]),
    "b == 1.0": (lambda b, f: b == 1.0, ["==", ABOVE, 1.0]),
    "b >= f": (lambda b, f: b >= f, [">=", ABOVE, "f"]),
    "f > True": (lambda b, f: f > True, [">", "f", True]),
    "f != b": (lambda b, f: f != b, ["!=", "f", ABOVE]),
}


def _operands(sink: list[SinkItem]) -> tuple[ConcolicBool, ConcolicFloat]:
    return (
        ConcolicBool(True, expression=ABOVE, sink=sink),
        ConcolicFloat(2.0, expression="f", sink=sink),
    )


@pytest.mark.parametrize(("call", "node"), MIXED.values(), ids=list(MIXED))
def test_a_bool_meeting_a_float_is_a_tracked_float_on_pythons_answer(
    call: Callable[[int, float], object], node: list[object]
) -> None:
    sink: list[SinkItem] = []

    answer = call(*_operands(sink))

    assert isinstance(answer, ConcolicFloat)
    assert answer == call(True, 2.0)
    assert answer.expression == node
    # a division by a tracked bool or float forks on it first; nothing else is recorded
    assert all(isinstance(item, Branch) for item in sink)


@pytest.mark.parametrize(("call", "node"), COMPARED.values(), ids=list(COMPARED))
def test_a_bool_compared_with_a_float_is_a_tracked_bool(
    call: Callable[[int, float], object], node: list[object]
) -> None:
    sink: list[SinkItem] = []

    answer = call(*_operands(sink))

    assert isinstance(answer, ConcolicBool)
    assert repr(answer) == repr(call(True, 2.0))
    assert answer.expression == node
    assert sink == []


def test_a_plain_float_on_the_left_of_a_tracked_bool_is_floats_own_and_records_nothing() -> None:
    sink: list[SinkItem] = []
    b, _ = _operands(sink)

    answer = 2.5 * b

    assert type(answer) is float
    assert answer == 2.5
    assert sink == []


def test_a_float_divided_by_a_false_bool_raises_with_its_fork_recorded() -> None:
    sink: list[SinkItem] = []
    b = ConcolicBool(False, expression=ABOVE, sink=sink)
    f = ConcolicFloat(2.0, expression="f", sink=sink)

    with pytest.raises(ZeroDivisionError):
        f / b

    # the zero fork of a bool divisor is its own condition, as `if` would test it
    assert [(item.expression, item.taken) for item in sink if isinstance(item, Branch)] == [
        (ABOVE, False)
    ]

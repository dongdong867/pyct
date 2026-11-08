"""A watched call: a tracked argument and a plain answer record a downgrade named as written."""

import math
import sys
from typing import Any

import pytest

from pyct.core.entry import watch
from pyct.core.entry.watch import answer, first, given
from pyct.core.foundation.branch import Downgrade, SinkItem
from pyct.core.numbers.ints import ConcolicInt
from pyct.core.strs.strs import ConcolicStr


@pytest.fixture(autouse=True)
def no_call_open() -> None:
    watch.forget()


def tracked(value: int, sink: list[SinkItem]) -> ConcolicInt:
    return ConcolicInt.made(value, expression="x", sink=sink)


def lost(sink: list[SinkItem]) -> list[tuple[str, int]]:
    """Each downgrade in the sink, by name and line."""
    return [(item.name, item.site.line) for item in sink if isinstance(item, Downgrade)]


def here() -> int:
    """The line that called this."""
    return sys._getframe(1).f_lineno


def test_a_tracked_argument_and_a_plain_answer_record_the_call_s_name_at_its_site() -> None:
    sink: list[SinkItem] = []
    x = tracked(3, sink)

    line = here() + 1
    written = answer(bin(first(x)), "bin")

    assert written == "0b11"
    assert lost(sink) == [("bin", line)]


@pytest.mark.parametrize(
    "result",
    [
        pytest.param([1, (2.5, "a")], id="a container of plain values"),
        pytest.param({"k": True}, id="a dict of plain values"),
        pytest.param(frozenset({1}), id="a frozenset"),
        pytest.param([], id="an empty list"),
    ],
)
def test_a_container_of_only_plain_values_is_a_plain_answer(result: Any) -> None:
    sink: list[SinkItem] = []

    answer(first(tracked(3, sink)) and result, "f")

    assert [name for name, _ in lost(sink)] == ["f"]


@pytest.mark.parametrize(
    "result",
    [
        pytest.param(None, id="None"),
        pytest.param(object(), id="an object"),
        pytest.param([1, object()], id="a list holding an object"),
    ],
)
def test_an_answer_that_holds_no_plain_value_alone_records_nothing(result: Any) -> None:
    sink: list[SinkItem] = []

    answer(first(tracked(3, sink)) and result, "f")

    assert lost(sink) == []


def test_a_tracked_answer_records_nothing() -> None:
    sink: list[SinkItem] = []
    x = tracked(3, sink)

    answer((lambda v: v)(first(x)), "itself")

    assert lost(sink) == []


def test_a_call_of_plain_arguments_records_nothing() -> None:
    sink: list[SinkItem] = []

    assert answer(max(first(1), given(2)), "max") == 2
    assert lost(sink) == []


def test_a_later_tracked_argument_counts_and_the_first_one_s_sink_takes_the_loss() -> None:
    sink: list[SinkItem] = []
    s = ConcolicStr.made("ab", expression="s", sink=[])
    x = tracked(4, sink)

    answer(math.gcd(first(6), given(x), 2 if given(s) else 0), "math.gcd")

    assert [name for name, _ in lost(sink)] == ["math.gcd"]


def test_a_downgrade_inside_the_call_takes_the_place_of_the_call_s_own() -> None:
    sink: list[SinkItem] = []
    x = tracked(3, sink)

    answer((lambda v: v ^ 0)(first(x)), "flip")

    assert [name for name, _ in lost(sink)] == ["__xor__"]


def test_a_downgrade_in_an_argument_before_the_last_leaves_the_call_s_own() -> None:
    sink: list[SinkItem] = []
    x = tracked(3, sink)

    answer(math.gcd(first(x), given(x ^ 0)), "math.gcd")

    assert [name for name, _ in lost(sink)] == ["__xor__", "math.gcd"]


def test_a_call_inside_an_argument_answers_for_itself() -> None:
    sink: list[SinkItem] = []
    x = tracked(3, sink)

    answer(str(first(answer(bin(first(x)), "bin"))), "str")

    # bin lost x; str was handed bin's plain answer
    assert [name for name, _ in lost(sink)] == ["bin"]


def test_a_call_that_raised_leaves_the_next_call_its_own() -> None:
    sink: list[SinkItem] = []
    x = tracked(3, sink)

    with pytest.raises(ZeroDivisionError):
        answer(divmod(first(x), given(0)), "divmod")
    answer(abs(first(-4)), "abs")

    assert lost(sink) == []

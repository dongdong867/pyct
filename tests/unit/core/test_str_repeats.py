"""A tracked str repeated: by a plain count up to the bound a tracked str, by no copies the plain
empty string, and past the bound or by any other count str's own answer and a downgrade."""

import operator
from collections.abc import Callable

import pytest

from pyct.core.branch import Downgrade, SinkItem
from pyct.core.ints import ConcolicInt
from pyct.core.str_repeats import MOST_COPIES
from pyct.core.strs import ConcolicStr
from pyct.core.values import raised_by_target


def _s(value: str, sink: list[SinkItem]) -> ConcolicStr:
    return ConcolicStr.made(value, expression="s", sink=sink)


@pytest.mark.parametrize(
    ("repeat", "form"),
    [
        (lambda s: s * 3, ["*", "s", 3]),
        (lambda s: 3 * s, ["*", 3, "s"]),
        (lambda s: s * True, ["*", "s", 1]),
        (lambda s: s * MOST_COPIES, ["*", "s", MOST_COPIES]),
    ],
)
def test_a_plain_count_up_to_the_bound_is_a_tracked_str(
    repeat: Callable[[ConcolicStr], object], form: list[object]
) -> None:
    sink: list[SinkItem] = []

    answer = repeat(_s("ab", sink))

    assert type(answer) is ConcolicStr
    assert str.__str__(answer) == repeat("ab")  # pyrefly: ignore[bad-argument-type]
    assert answer.expression == form
    assert sink == []


def test_a_repeat_keeps_the_length_range_scaled() -> None:
    sink: list[SinkItem] = []
    s = _s("ab", sink)
    s.__dict__["span"] = (1, 4)

    answer = s * 3

    assert isinstance(answer, ConcolicStr) and answer.span == (3, 12)


@pytest.mark.parametrize("count", [0, -2, False])
def test_no_copies_is_python_s_empty_string_plain(count: int) -> None:
    sink: list[SinkItem] = []

    answers = [_s("ab", sink) * count, count * _s("ab", sink)]

    assert [type(answer) for answer in answers] == [str, str]
    assert answers == ["", ""]
    assert sink == []


@pytest.mark.parametrize(
    ("repeat", "name"),
    [
        (lambda s: s * (MOST_COPIES + 1), "__mul__"),
        (lambda s: (MOST_COPIES + 1) * s, "__rmul__"),
        (lambda s: s * ConcolicInt.made(2, expression="n", sink=[]), "__mul__"),
    ],
)
def test_past_the_bound_or_a_tracked_count_is_str_s_answer_and_a_downgrade(
    repeat: Callable[[object], object], name: str
) -> None:
    sink: list[SinkItem] = []

    answer = repeat(_s("ab", sink))

    assert type(answer) is str
    assert answer == repeat("ab")
    assert [item.name for item in sink if isinstance(item, Downgrade)] == [name]


@pytest.mark.parametrize("count", [2.0, "2", None, 2**64])
def test_a_count_python_refuses_raises_python_s_error_as_the_target_s(count: object) -> None:
    sink: list[SinkItem] = []

    with pytest.raises(Exception) as raised:
        operator.mul(_s("ab", sink), count)

    with pytest.raises(Exception) as plain:
        operator.mul("ab", count)  # pyrefly: ignore[no-matching-overload]
    assert (type(raised.value), str(raised.value)) == (type(plain.value), str(plain.value))
    assert raised_by_target(raised.value)
    assert sink == []

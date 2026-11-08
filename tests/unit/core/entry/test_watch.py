"""A watched call: a tracked argument and a plain answer record a downgrade named as written."""

import contextlib
import math
import sys
import threading
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


def _catching(value: Any) -> int:
    """A callee whose own watched call raises, and which catches it and answers plainly."""
    with contextlib.suppress(ZeroDivisionError):
        answer(divmod(first(value), given(0)), "divmod")
    return 1


def test_a_call_whose_callee_caught_a_raise_is_judged_by_its_own_argument() -> None:
    sink: list[SinkItem] = []
    x = tracked(3, sink)

    # a plain list goes in, and the callee's divmod, left open, took the tracked x inside it
    answer(first_of(first([x])), "first_of")
    assert lost(sink) == []

    # x goes in tracked, and the callee's divmod, left open, took a plain 7
    answer(two(first(x)), "two")
    assert [name for name, _ in lost(sink)] == ["two"]


def first_of(items: list[object]) -> int:
    return _catching(items[0])


def two(_value: object) -> int:
    _catching(7)
    return 2


def test_each_thread_keeps_its_own_open_calls() -> None:
    sink: list[SinkItem] = []
    x = tracked(3, sink)
    opened, pushed, done = threading.Event(), threading.Event(), threading.Event()

    def other() -> None:
        # a plain call opens in another thread while this thread's call is open, and answers
        # after it
        opened.wait(5)
        first(5)
        pushed.set()
        done.wait(5)
        answer(2, "other")

    def waits(_value: object) -> int:
        opened.set()
        pushed.wait(5)
        return 2

    thread = threading.Thread(target=other)
    thread.start()
    answer(waits(first(x)), "waits")
    done.set()
    thread.join(5)

    assert [name for name, _ in lost(sink)] == ["waits"]


def test_an_answer_that_holds_itself_is_read_once() -> None:
    sink: list[SinkItem] = []
    held: Any = [1]
    held.append(held)

    assert answer(first(tracked(3, sink)) and held, "f") is held
    assert [name for name, _ in lost(sink)] == ["f"]


def test_a_call_left_open_at_a_site_is_dropped_when_the_site_runs_again() -> None:
    sink: list[SinkItem] = []
    x = tracked(3, sink)

    for _ in range(10_000):
        with contextlib.suppress(ZeroDivisionError):
            answer(divmod(first(1), given(0)), "divmod")

    assert len(watch._calls()) == 1
    # the frame's next call answers for itself, not for a call left open with a plain argument
    answer(bin(first(x)), "bin")
    assert [name for name, _ in lost(sink)] == ["bin"]


def _leaves_one_open() -> None:
    with contextlib.suppress(ZeroDivisionError):
        answer(divmod(first(1), given(0)), "divmod")


def test_calls_left_open_by_frames_that_returned_are_kept_to_a_bound() -> None:
    sink: list[SinkItem] = []
    x = tracked(3, sink)

    for _ in range(watch.MOST_OPEN + 10):
        _leaves_one_open()

    assert len(watch._calls()) == watch.MOST_OPEN
    answer(bin(first(x)), "bin")
    assert [name for name, _ in lost(sink)] == ["bin"]


def test_forget_drops_the_calls_every_thread_left_open() -> None:
    sink: list[SinkItem] = []
    opened, forgotten = threading.Event(), threading.Event()
    seen: list[object] = []

    def other() -> None:
        first(tracked(3, sink))
        opened.set()
        forgotten.wait(5)
        # the call opened before the forget is gone, so its answer records nothing
        seen.append(answer(2, "other"))
        seen.append(len(watch._calls()))

    thread = threading.Thread(target=other)
    thread.start()
    opened.wait(5)
    watch.forget()
    forgotten.set()
    thread.join(5)

    assert seen == [2, 0]
    assert lost(sink) == []

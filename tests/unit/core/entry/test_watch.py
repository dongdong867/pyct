"""A watched call: a tracked argument and a plain answer record a downgrade named as written."""

import builtins
import contextlib
import functools
import math
import sys
import threading
from collections.abc import Callable
from typing import Any

import pytest

from pyct.core.entry import watch
from pyct.core.entry.watch import answer, called, given
from pyct.core.foundation import escapes
from pyct.core.foundation.branch import Downgrade, SinkItem
from pyct.core.numbers.ints import ConcolicInt
from pyct.core.strs.strs import ConcolicStr
from pyct.intercept.wrap import bound_builtins


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
    written = answer(called(bin)(given(x)), "bin")

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

    answer(called(lambda _v: result)(given(tracked(3, sink))), "f")

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

    answer(called(lambda _v: result)(given(tracked(3, sink))), "f")

    assert lost(sink) == []


def test_a_tracked_answer_records_nothing() -> None:
    sink: list[SinkItem] = []
    x = tracked(3, sink)

    answer(called(lambda v: v)(given(x)), "itself")

    assert lost(sink) == []


def test_a_call_of_plain_arguments_records_nothing() -> None:
    sink: list[SinkItem] = []

    assert answer(called(max)(given(1), given(2)), "max") == 2
    assert lost(sink) == []


def test_a_later_tracked_argument_counts_and_the_first_one_s_sink_takes_the_loss() -> None:
    sink: list[SinkItem] = []
    s = ConcolicStr.made("ab", expression="s", sink=[])
    x = tracked(4, sink)

    answer(called(math.gcd)(given(6), given(x), 2 if given(s) else 0), "math.gcd")

    assert [name for name, _ in lost(sink)] == ["math.gcd"]


def test_a_downgrade_inside_the_call_takes_the_place_of_the_call_s_own() -> None:
    sink: list[SinkItem] = []
    x = tracked(3, sink)

    answer(called(lambda v: v ^ 0)(given(x)), "flip")

    assert [name for name, _ in lost(sink)] == ["__xor__"]


def test_a_downgrade_in_an_argument_before_the_last_leaves_the_call_s_own() -> None:
    sink: list[SinkItem] = []
    x = tracked(3, sink)

    answer(called(math.gcd)(given(x), given(x ^ 0)), "math.gcd")

    assert [name for name, _ in lost(sink)] == ["__xor__", "math.gcd"]


def test_a_call_inside_an_argument_answers_for_itself() -> None:
    sink: list[SinkItem] = []
    x = tracked(3, sink)

    answer(called(str)(given(answer(called(bin)(given(x)), "bin"))), "str")

    # bin lost x; str was handed bin's plain answer
    assert [name for name, _ in lost(sink)] == ["bin"]


def test_a_call_that_raised_leaves_the_next_call_its_own() -> None:
    sink: list[SinkItem] = []
    x = tracked(3, sink)

    with pytest.raises(ZeroDivisionError):
        answer(called(divmod)(given(x), given(0)), "divmod")
    answer(called(abs)(given(-4)), "abs")

    assert lost(sink) == []


def _catching(value: Any) -> int:
    """A callee whose own watched call raises, and which catches it and answers plainly."""
    with contextlib.suppress(ZeroDivisionError):
        answer(called(divmod)(given(value), given(0)), "divmod")
    return 1


def test_a_call_whose_callee_caught_a_raise_is_judged_by_its_own_argument() -> None:
    sink: list[SinkItem] = []
    x = tracked(3, sink)

    # a function that gives x goes in, and the callee's divmod, left open, took x inside it
    answer(called(read)(given(lambda: x)), "read")
    assert lost(sink) == []

    # x goes in tracked, and the callee's divmod, left open, took a plain 7
    answer(called(two)(given(x)), "two")
    assert [name for name, _ in lost(sink)] == ["two"]


def read(give: Callable[[], object]) -> int:
    return _catching(give())


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
        called(abs)
        pushed.set()
        done.wait(5)
        answer(2, "other")

    def waits(_value: object) -> int:
        opened.set()
        pushed.wait(5)
        return 2

    thread = threading.Thread(target=other)
    thread.start()
    answer(called(waits)(given(x)), "waits")
    done.set()
    thread.join(5)

    assert [name for name, _ in lost(sink)] == ["waits"]


def test_an_answer_that_holds_itself_is_read_once() -> None:
    sink: list[SinkItem] = []
    held: Any = [1]
    held.append(held)

    assert answer(called(lambda _v: held)(given(tracked(3, sink))), "f") is held
    assert [name for name, _ in lost(sink)] == ["f"]


def test_a_call_left_open_at_a_site_is_dropped_when_the_site_runs_again() -> None:
    sink: list[SinkItem] = []
    x = tracked(3, sink)

    for _ in range(10_000):
        with contextlib.suppress(ZeroDivisionError):
            answer(called(divmod)(given(1), given(0)), "divmod")

    assert len(watch._calls()) == 1
    # the frame's next call answers for itself, not for a call left open with a plain argument
    answer(called(bin)(given(x)), "bin")
    assert [name for name, _ in lost(sink)] == ["bin"]


def _raises_from_its_own_call(value: int) -> tuple[int, int]:
    """A callee whose own watched call raises out of it, left open."""
    return answer(called(divmod)(given(value), 0), "divmod")


def test_a_site_that_runs_again_drops_the_calls_its_callee_left_open_too() -> None:
    for _ in range(1_000):
        with contextlib.suppress(ZeroDivisionError):
            answer(called(_raises_from_its_own_call)(given(1)), "raises")

    # each pass left this frame's call open, and the callee's above it
    assert len(watch._calls()) == 2


def _leaves_one_open() -> None:
    with contextlib.suppress(ZeroDivisionError):
        answer(called(divmod)(given(1), given(0)), "divmod")


def test_calls_left_open_by_frames_that_returned_are_kept_to_a_bound() -> None:
    sink: list[SinkItem] = []
    x = tracked(3, sink)

    for _ in range(watch.MOST_OPEN + 10):
        _leaves_one_open()

    assert len(watch._calls()) == watch.MOST_OPEN
    answer(called(bin)(given(x)), "bin")
    assert [name for name, _ in lost(sink)] == ["bin"]


def test_forget_drops_the_calls_every_thread_left_open() -> None:
    sink: list[SinkItem] = []
    opened, forgotten = threading.Event(), threading.Event()
    seen: list[object] = []

    def other() -> None:
        called(abs)
        given(tracked(3, sink))
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


def _in_the_package(source: str, name: str) -> Any:
    """What ``source`` defines under ``name``, run as a module of the target's package runs:
    with the builtins pyct binds."""
    space: dict[str, Any] = {"__builtins__": bound_builtins(), "__name__": "shop.helper"}
    exec(compile(source, "shop/helper.py", "exec"), space)
    return space[name]


# a callee that loses its argument: bin, run inside it unwatched, gives back a plain str
IS_BIG = "def is_big(v):\n    return bin(v).count('1') > 1\n"
HELPER = """
import functools

def is_big(v):
    return bin(v).count('1') > 1

class Sizes:
    def is_big(self, v):
        return bin(v).count('1') > 1

    def __call__(self, v):
        return bin(v).count('1') > 1

partial = functools.partial(is_big)
"""


def _decorated(function: Callable[[Any], Any]) -> Callable[[Any], Any]:
    """``function`` behind a wrapper of a decorator outside the target's package, as a library
    writes one."""

    @functools.wraps(function)
    def wrapper(value: Any) -> Any:
        return function(value)

    return wrapper


class _Answers:
    """A callable outside the target's package whose every other attribute is a function of
    the package's, as a mock's would be."""

    def __call__(self, value: object) -> int:
        return bin(value).count("1")  # pyrefly: ignore[bad-argument-type]

    def __getattr__(self, name: str) -> object:
        return _in_the_package(HELPER, "is_big")


@pytest.mark.parametrize(
    "callee",
    [
        pytest.param(lambda: _in_the_package(HELPER, "is_big"), id="a function"),
        pytest.param(lambda: _in_the_package(HELPER, "Sizes")().is_big, id="a bound method"),
        pytest.param(lambda: _in_the_package(HELPER, "partial"), id="a partial"),
        pytest.param(lambda: _in_the_package(HELPER, "Sizes")(), id="an object's __call__"),
        pytest.param(
            lambda: _decorated(_in_the_package(HELPER, "is_big")), id="a library's decorator"
        ),
        pytest.param(
            lambda: functools.lru_cache(_in_the_package(HELPER, "is_big")), id="lru_cache"
        ),
        pytest.param(
            lambda: functools.singledispatch(_in_the_package(HELPER, "is_big")),
            id="singledispatch",
        ),
    ],
)
def test_a_call_into_the_target_s_package_is_not_judged(callee: Callable[[], Any]) -> None:
    sink: list[SinkItem] = []
    function = callee()

    answer(called(function)(given(tracked(3, sink))), "is_big")

    assert lost(sink) == []


def test_a_callable_s_own_attribute_lookup_does_not_place_it() -> None:
    sink: list[SinkItem] = []

    answer(called(_Answers())(given(tracked(3, sink))), "answers")

    assert [name for name, _ in lost(sink)] == ["answers"]


def test_a_call_into_the_target_s_package_is_not_judged_while_len_is_replaced() -> None:
    sink: list[SinkItem] = []
    function = _in_the_package(HELPER, "is_big")
    python_len = builtins.len
    # the target puts a `len` of its own in `builtins`, which its modules then find
    builtins.len = lambda _value: 0
    try:
        answer(called(function)(given(tracked(3, sink))), "is_big")
    finally:
        builtins.len = python_len

    assert lost(sink) == []


def test_a_call_outside_the_target_s_package_is_judged() -> None:
    sink: list[SinkItem] = []
    # the same function, run with Python's own builtins, as a library's module runs
    space: dict[str, Any] = {}
    exec(compile(IS_BIG, "lib/helper.py", "exec"), space)

    answer(called(space["is_big"])(given(tracked(3, sink))), "is_big")

    assert [name for name, _ in lost(sink)] == ["is_big"]


def test_a_callee_that_forked_inside_adds_no_downgrade() -> None:
    sink: list[SinkItem] = []

    def forks(_value: object) -> int:
        # a fork the call made, as the tally counts it
        escapes.RECORDED[0] += 1
        return 1

    answer(called(forks)(given(tracked(3, sink))), "forks")

    assert lost(sink) == []


@pytest.mark.parametrize(
    ("argument", "counts"),
    [
        pytest.param(lambda x: [x, 1], True, id="a list"),
        pytest.param(lambda x: (1, x), True, id="a tuple"),
        pytest.param(lambda x: {x: 1}, True, id="a dict's key"),
        pytest.param(lambda x: {"k": x}, True, id="a dict's value"),
        pytest.param(lambda x: [[x]], False, id="nested two levels"),
        pytest.param(lambda x: {x}, False, id="a set"),
        pytest.param(lambda x: [0] * (watch.MOST_ITEMS - 1) + [x], True, id="the last item read"),
        pytest.param(lambda x: [0] * watch.MOST_ITEMS + [x], False, id="past the items read"),
    ],
)
def test_a_list_tuple_or_dict_passed_to_the_call_counts_one_level_deep(
    argument: Callable[[ConcolicInt], Any], counts: bool
) -> None:
    sink: list[SinkItem] = []

    answer(called(str)(given(argument(tracked(3, sink)))), "str")

    assert [name for name, _ in lost(sink)] == (["str"] if counts else [])


def test_a_bytes_answer_is_plain() -> None:
    sink: list[SinkItem] = []
    x = tracked(3, sink)

    answer(called(bytes)(given([x, 1])), "bytes")

    assert [name for name, _ in lost(sink)] == ["bytes"]

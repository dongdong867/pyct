"""While an input that records loss runs is live, a watched call that loses a tracked value records
its run: each argument the watch was given, as it was given, the answer, and the callee's names."""

import contextlib
import sys
from collections.abc import Iterator

import pytest

from pyct.core.entry import losses, pieces, watch
from pyct.core.entry.pieces import MOST_RUNS
from pyct.core.entry.watch import answer, called, given
from pyct.core.foundation.branch import (
    Callee,
    Changed,
    GoingIn,
    LossKind,
    LossRun,
    SinkItem,
    Site,
)
from pyct.core.numbers.ints import ConcolicInt


@pytest.fixture(autouse=True)
def no_call_open() -> None:
    watch.forget()


@contextlib.contextmanager
def live(*, recording: bool = True) -> Iterator[list[SinkItem]]:
    """A live input whose sink is the list yielded, its loss runs recorded with ``recording``."""
    sink: list[SinkItem] = []
    pieces.start(sink)
    if recording:
        losses.start(sink)
    try:
        yield sink
    finally:
        losses.forget()
        pieces.forget()


def runs(sink: list[SinkItem]) -> list[LossRun]:
    return [item for item in sink if isinstance(item, LossRun)]


def here() -> int:
    """The line after the one that called this."""
    return sys._getframe(1).f_lineno + 1


def counted(items: list[object]) -> int:
    """A Python function outside the target's package, which reads its list as it is."""
    items.append(0)
    return len(items)


def test_a_watched_call_s_loss_records_its_arguments_its_answer_and_its_callee() -> None:
    with live() as sink:
        x = ConcolicInt.made(3, expression="x", sink=sink)
        line = here()
        written = answer(called(bin)(given(x)), "bin")

    assert written == "0b11"
    [run] = runs(sink)
    assert run == LossRun(
        Site(__file__, line, 18),
        "bin",
        LossKind.CALL,
        (GoingIn("arg1", "3", tracked=True),),
        (Changed("answer", '"0b11"'),),
        Callee("builtins", "bin"),
    )


def test_a_python_callee_is_named_with_its_code_s_place_and_its_arguments_as_given() -> None:
    with live() as sink:
        items: list[object] = [ConcolicInt.made(3, expression="x", sink=sink)]
        _ = answer(called(counted)(given(items)), "counted")

    [run] = runs(sink)
    assert run.going_in == (GoingIn("arg1", "[3]", tracked=False),)
    assert run.changed == (Changed("answer", "2"),)
    code = counted.__code__
    assert run.callee == Callee(__name__, "counted", code.co_filename, code.co_firstlineno)


def test_a_method_written_in_c_is_named_by_its_class() -> None:
    with live() as sink:
        x = ConcolicInt.made(3, expression="x", sink=sink)
        _ = answer(called(str.zfill)(given("7"), given(x)), "str.zfill")

    [run] = runs(sink)
    assert run.callee == Callee("builtins", "str.zfill")
    assert [each.value for each in run.going_in] == ['"7"', "3"]


def test_a_call_site_writes_its_arguments_for_its_first_calls_alone() -> None:
    with live() as sink:
        for each in range(MOST_RUNS + 2):
            x = ConcolicInt.made(each, expression="x", sink=sink)
            _ = answer(called(bin)(given(x)), "bin")

    assert [run.going_in[0].value for run in runs(sink)] == [str(each) for each in range(MOST_RUNS)]


def test_an_argument_that_is_not_plain_json_records_no_run() -> None:
    with live() as sink:
        x = ConcolicInt.made(3, expression="x", sink=sink)
        _ = answer(called(isinstance)(given(x), given(int)), "isinstance")

    assert runs(sink) == []


def test_with_the_recording_off_a_watched_loss_records_no_run() -> None:
    with live(recording=False) as sink:
        x = ConcolicInt.made(3, expression="x", sink=sink)
        _ = answer(called(bin)(given(x)), "bin")

    assert runs(sink) == []
    assert len(sink) == 1

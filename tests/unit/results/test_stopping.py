"""The stop timer: the cause analysis ends at its stop wherever it is, and leaves nothing armed."""

import signal
import textwrap
import time
from pathlib import Path

import pytest

from pyct.results import why as why_module
from pyct.results.graphs import OutOfTimeError
from pyct.results.stopping import stopping
from pyct.results.way import Flow
from pyct.results.why import Reason, Run, Walked, explain
from tests.unit.deadline_fires import DEADLINE_FIRES

SOURCE = """\
def f(x):
    y = int("x")
    if x > 0:
        return y
    return 0
"""


def module(tmp_path: Path) -> str:
    file = tmp_path / "m.py"
    file.write_text(textwrap.dedent(SOURCE))
    return str(file)


def armed() -> float:
    """The seconds left on the real-time timer, 0 when none is armed."""
    return signal.getitimer(signal.ITIMER_REAL)[0]


@DEADLINE_FIRES
def test_a_slow_step_still_ends_at_the_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    file = module(tmp_path)
    handler = signal.getsignal(signal.SIGALRM)
    slow = Flow.marked

    def sleeping(flow: Flow, *args: object) -> frozenset[int]:
        # a step that checks no clock and would run for ten seconds
        time.sleep(10)
        return slow(flow, *args)  # pyrefly: ignore[bad-argument-type]

    monkeypatch.setattr(Flow, "marked", sleeping)
    walked = [Walked(forks=(), failed=True, lines=frozenset({2}))]
    stop_at = time.monotonic() + 0.2

    entries = explain(file, frozenset({3, 4, 5}), frozenset({2}), Run(walked, {}, stop_at=stop_at))
    ended = time.monotonic()

    assert [(entry.lines, entry.reason) for entry in entries] == [
        ((3, 4, 5), Reason.NOT_WORKED_OUT)
    ]
    assert ended - stop_at < 0.1, ended - stop_at
    assert armed() == 0
    assert signal.getsignal(signal.SIGALRM) is handler


def test_a_run_with_no_stop_arms_nothing() -> None:
    handler = signal.getsignal(signal.SIGALRM)

    with stopping(None, time.monotonic):
        assert armed() == 0
        assert signal.getsignal(signal.SIGALRM) is handler


def test_the_timer_is_disarmed_and_the_handler_restored_when_the_block_raises() -> None:
    handler = signal.getsignal(signal.SIGALRM)

    with pytest.raises(ValueError), stopping(time.monotonic() + 60, time.monotonic):
        assert armed() > 0
        raise ValueError

    assert armed() == 0
    assert signal.getsignal(signal.SIGALRM) is handler


def test_another_pending_timer_is_left_alone() -> None:
    # pyct's deadline alarm, or anyone's: the stop does not take the timer over
    signal.setitimer(signal.ITIMER_REAL, 60)
    try:
        with stopping(time.monotonic() + 1, time.monotonic):
            assert 59 < armed() <= 60
        assert 59 < armed() <= 60
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


@DEADLINE_FIRES
def test_a_stop_already_past_fires_at_once_and_only_inside_the_block() -> None:
    with pytest.raises(OutOfTimeError), stopping(time.monotonic() - 1, time.monotonic):
        time.sleep(1)

    assert armed() == 0


@DEADLINE_FIRES
def test_the_lines_left_by_a_stop_that_fired_are_each_in_one_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    file = module(tmp_path)
    walked = [Walked(forks=(), failed=True, lines=frozenset({2}))]
    # the timer fires at once; the steps' own clock checks see no stop
    monkeypatch.setattr(why_module, "clock", lambda: 0.0)

    entries = explain(file, frozenset({1, 3, 4, 5}), frozenset({2}), Run(walked, {}, stop_at=-1.0))

    assert sorted(line for entry in entries for line in entry.lines) == [1, 3, 4, 5]
    assert {entry.reason for entry in entries} == {Reason.NOT_WORKED_OUT}

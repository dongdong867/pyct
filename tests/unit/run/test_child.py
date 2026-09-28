"""The input's own process, served for real in a child this test forks."""

import asyncio
import mmap
import os
import signal
import sys
import threading
import time
import types
from collections.abc import Callable
from contextlib import AbstractContextManager

import pytest

from pyct.execution.deadline import DeadlineError, deadline
from pyct.results.failure import FailureKind
from pyct.run import child
from pyct.run.child import serve, settle
from pyct.run.journal import CAPACITY, JournalWriter, read
from pyct.run.process import STOP_SIGNALS


def test_a_raise_out_of_pyct_s_own_code_is_a_pyct_bug_on_the_input_s_line() -> None:
    def broken(watch: JournalWriter) -> None:
        raise RuntimeError("pyct broke")

    with mmap.mmap(-1, CAPACITY) as buffer:
        pid = os.fork()
        if pid == 0:
            serve(JournalWriter(buffer), broken)
        _, status = os.waitpid(pid, 0)
        reading = read(buffer)

    assert os.waitstatus_to_exitcode(status) == 0
    assert reading.ended
    assert reading.end is not None
    assert reading.end.kind is FailureKind.PYCT_BUG
    assert reading.end.detail == "RuntimeError: pyct broke"
    assert reading.end.traceback is not None
    assert "broken" in reading.end.traceback


def test_the_input_s_process_takes_each_stop_signal_by_its_default_action() -> None:
    previous = signal.signal(signal.SIGTERM, lambda number, frame: None)
    try:
        with mmap.mmap(-1, CAPACITY) as buffer:
            pid = os.fork()
            if pid == 0:
                settle(JournalWriter(buffer))
                defaults = all(signal.getsignal(n) is signal.SIG_DFL for n in STOP_SIGNALS)
                unblocked = not signal.pthread_sigmask(signal.SIG_BLOCK, set()) & STOP_SIGNALS
                os._exit(0 if defaults and unblocked else 1)
            _, status = os.waitpid(pid, 0)
    finally:
        signal.signal(signal.SIGTERM, previous)

    assert os.waitstatus_to_exitcode(status) == 0


def settled_then(step: Callable[[], None]) -> int:
    """Fork a child that settles as an input's process, then runs ``step``: its exit code.

    The child exits 0 once the step is done, and 3 when a DeadlineError got out of it. It
    exits as the input's process does, so coverage.py saves what it measured there.
    """
    with mmap.mmap(-1, CAPACITY) as buffer:
        pid = os.fork()
        if pid == 0:
            settle(JournalWriter(buffer))
            try:
                step()
            except DeadlineError:
                child._EXIT(3)
            child._EXIT(0)
        _, status = os.waitpid(pid, 0)
    return os.waitstatus_to_exitcode(status)


def alarm_after_the_block() -> None:
    with deadline(time.monotonic() + 10):
        pass
    # the kernel timer's SIGALRM, come late, after its block has ended
    os.kill(os.getpid(), signal.SIGALRM)
    for _ in range(1000):
        pass


def test_a_late_alarm_in_the_input_s_process_neither_ends_it_nor_raises() -> None:
    assert settled_then(alarm_after_the_block) == 0


def hang_until_the_deadline() -> None:
    try:
        with deadline(time.monotonic() + 0.05):
            while True:
                pass
    except DeadlineError:
        return
    child._EXIT(1)


@pytest.mark.usefixtures("deadline_fires_in_a_child")
def test_the_input_s_own_alarm_still_ends_a_hang() -> None:
    assert settled_then(hang_until_the_deadline) == 0


def test_the_input_s_deadline_starts_no_thread() -> None:
    def count_threads() -> None:
        with deadline(time.monotonic() + 10):
            running = threading.active_count()
        child._EXIT(0 if running == 1 else 1)

    assert settled_then(count_threads) == 0


def hang_after_an_import_takes_sigalrm() -> None:
    # the target's import installs a SIGALRM handler of its own
    signal.signal(signal.SIGALRM, lambda number, frame: None)
    running = 0
    try:
        with deadline(time.monotonic() + 0.05):
            running = threading.active_count()
            while True:
                pass
    except DeadlineError:
        child._EXIT(0 if running == 1 else 2)
    child._EXIT(1)


@pytest.mark.usefixtures("deadline_fires_in_a_child")
def test_the_input_s_process_keeps_the_alarm_its_target_s_import_took() -> None:
    assert settled_then(hang_after_an_import_takes_sigalrm) == 0


def late_alarm_into_the_next_block() -> None:
    with deadline(time.monotonic() + 10):
        pass
    with deadline(time.monotonic() + 10):
        # the first block's timer, come late, into a block whose instant is far off
        os.kill(os.getpid(), signal.SIGALRM)
        for _ in range(1000):
            pass


def test_a_late_alarm_in_a_process_pyct_owns_leaves_the_next_block_running() -> None:
    assert settled_then(late_alarm_into_the_next_block) == 0


def call_under(guard: AbstractContextManager[None]) -> None:
    """A call under a deadline, held by a frame of its own, as pyct's call of the target is."""
    with guard:
        time.sleep(0.001)


def spin_after_the_call() -> None:
    """Run past the deadline outside any block, where pyct's own clean-up would run."""
    end = time.monotonic() + 0.3
    while time.monotonic() < end:
        pass


def ctrl_c_as_the_timer_is_armed() -> None:
    real = signal.setitimer

    def arm_then_interrupt(
        which: int, seconds: float, interval: float = 0.0, /
    ) -> tuple[float, float]:
        armed = real(which, seconds, interval)
        if seconds:
            # a Ctrl-C Python handles as setitimer returns
            raise KeyboardInterrupt
        return armed

    signal.setitimer = arm_then_interrupt
    try:
        call_under(deadline(time.monotonic() + 0.1))
    except KeyboardInterrupt:
        pass
    finally:
        signal.setitimer = real
    spin_after_the_call()


def ctrl_c_as_the_way_out_begins() -> None:
    guard = deadline(time.monotonic() + 0.1)
    way_out = type(guard).__exit__.__code__

    def interrupt(frame: types.FrameType, event: str, arg: object) -> None:
        if event == "call" and frame.f_code is way_out:
            raise KeyboardInterrupt

    sys.settrace(interrupt)
    try:
        call_under(guard)
    except KeyboardInterrupt:
        pass
    finally:
        sys.settrace(None)
    spin_after_the_call()


@pytest.mark.usefixtures("deadline_fires_in_a_child")
@pytest.mark.parametrize("step", [ctrl_c_as_the_timer_is_armed, ctrl_c_as_the_way_out_begins])
def test_a_ctrl_c_at_a_block_s_edge_leaves_no_alarm_to_raise_after_it(
    step: Callable[[], None],
) -> None:
    assert settled_then(step) == 0


def alarm_on_a_ctrl_c_in_flight() -> None:
    try:
        with deadline(time.monotonic() + 0.05):
            try:
                raise KeyboardInterrupt
            except KeyboardInterrupt:
                # the alarm lands while the Ctrl-C is on its way out of the target
                end = time.monotonic() + 0.2
                while time.monotonic() < end:
                    pass
                raise
    except KeyboardInterrupt:
        return


@pytest.mark.usefixtures("deadline_fires_in_a_child")
def test_an_owned_alarm_that_lands_on_a_ctrl_c_leaves_it_to_go_on() -> None:
    assert settled_then(alarm_on_a_ctrl_c_in_flight) == 0


def hang_after_a_cancel_spans_the_deadline() -> None:
    try:
        with deadline(time.monotonic() + 0.05):
            try:
                raise asyncio.CancelledError
            except asyncio.CancelledError:
                # the alarm lands while the target handles its own cancel, then it hangs
                end = time.monotonic() + 0.1
                while time.monotonic() < end:
                    pass
            # a hang, bounded so the test fails rather than waits when no alarm comes
            while time.monotonic() < end + 2:
                pass
    except DeadlineError:
        return
    child._EXIT(1)


@pytest.mark.usefixtures("deadline_fires_in_a_child")
def test_an_owned_alarm_that_lands_on_a_target_s_own_base_exception_still_stops_it() -> None:
    assert settled_then(hang_after_a_cancel_spans_the_deadline) == 0


def hang_after_catching_a_ctrl_c_that_spans_the_deadline() -> None:
    try:
        with deadline(time.monotonic() + 0.05):
            try:
                raise KeyboardInterrupt
            except KeyboardInterrupt:
                end = time.monotonic() + 0.1
                while time.monotonic() < end:
                    pass
            # the stop is done with, so the alarm it held back comes now
            # a hang, bounded so the test fails rather than waits when no alarm comes
            while time.monotonic() < end + 2:
                pass
    except DeadlineError:
        return
    child._EXIT(1)


@pytest.mark.usefixtures("deadline_fires_in_a_child")
def test_an_owned_alarm_held_back_by_a_ctrl_c_comes_once_it_is_caught() -> None:
    assert settled_then(hang_after_catching_a_ctrl_c_that_spans_the_deadline) == 0

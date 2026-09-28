"""The input's own process, served for real in a child this test forks."""

import asyncio
import mmap
import os
import signal
import subprocess
import sys
import threading
import time
import types
from collections.abc import Callable
from contextlib import AbstractContextManager

import pytest

from pyct.execution import deadline as deadline_module
from pyct.execution.deadline import DeadlineError, deadline, own_the_alarm
from pyct.results.failure import FailureKind
from pyct.run import child
from pyct.run.child import serve, settle
from pyct.run.journal import CAPACITY, JournalWriter, read
from pyct.run.process import STOP_SIGNALS
from tests.unit.execution.ctrl_c_in_c import interrupted_call, spin_in_pyct
from tests.unit.execution.test_deadline import spin_until


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
                spin_until(time.monotonic() + 0.2)
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
                spin_until(time.monotonic() + 0.1)
            # a hang, bounded so the test fails rather than waits when no alarm comes
            spin_until(time.monotonic() + 2)
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
                spin_until(time.monotonic() + 0.1)
            # the stop is done with, so the alarm it held back comes now. A hang, bounded so the
            # test fails rather than waits when no alarm comes
            spin_until(time.monotonic() + 2)
    except DeadlineError:
        return
    child._EXIT(1)


@pytest.mark.usefixtures("deadline_fires_in_a_child")
def test_an_owned_alarm_held_back_by_a_ctrl_c_comes_once_it_is_caught() -> None:
    assert settled_then(hang_after_catching_a_ctrl_c_that_spans_the_deadline) == 0


def hold_a_ctrl_c_past_the_bound() -> None:
    started = time.monotonic()
    try:
        with deadline(started + 0.05):
            try:
                raise KeyboardInterrupt
            except KeyboardInterrupt:
                # a handler that never returns, bounded so the test fails rather than waits
                spin_until(started + 3)
    except DeadlineError:
        took = time.monotonic() - started
        child._EXIT(0 if 0.5 <= took < 1.5 else 2)
    child._EXIT(1)


@pytest.mark.usefixtures("deadline_fires_in_a_child")
def test_an_owned_alarm_held_back_by_a_ctrl_c_that_never_leaves_comes_after_a_bound() -> None:
    assert settled_then(hold_a_ctrl_c_past_the_bound) == 0


def owned_ctrl_c_during_a_c_call(name: str) -> None:
    # a process pyct owns, as the command line's, where a Ctrl-C raises as it does anywhere
    own_the_alarm()
    started = time.monotonic()
    try:
        interrupted_call(name)
    except KeyboardInterrupt:
        # the call returned after the hold would have run out, counted from the deadline
        child._EXIT(0 if time.monotonic() - started > 0.65 else 2)
    child._EXIT(3)


@pytest.mark.usefixtures("deadline_fires_in_a_child")
@pytest.mark.parametrize("name", ["total", "total_then_finally"])
def test_an_owned_ctrl_c_during_a_c_call_that_outlives_the_deadline_reaches_the_caller(
    name: str,
) -> None:
    pid = os.fork()
    if pid == 0:
        owned_ctrl_c_during_a_c_call(name)
    _, status = os.waitpid(pid, 0)

    assert os.waitstatus_to_exitcode(status) == 0


def hang_in_pyct_s_own_frames() -> None:
    spin = spin_in_pyct()
    started = time.monotonic()
    try:
        with deadline(started + 0.05):
            spin(started + 2)
    except DeadlineError:
        child._EXIT(0 if time.monotonic() - started < 0.3 else 2)
    child._EXIT(1)


@pytest.mark.usefixtures("deadline_fires_in_a_child")
def test_an_owned_hang_in_pyct_s_own_frames_ends_near_its_deadline() -> None:
    assert settled_then(hang_in_pyct_s_own_frames) == 0


def ctrl_c_after_an_alarm_held_in_pyct_s_frames() -> None:
    own_the_alarm()
    spin = spin_in_pyct()
    at = time.monotonic() + 0.05
    subprocess.Popen(["sh", "-c", f"sleep 0.3; kill -INT {os.getpid()}"])
    try:
        with deadline(at):
            # pyct's own work as the deadline comes, until the alarm is held there once, then
            # one long C call a Ctrl-C lands in
            spin(at + 1, deadline_module._OWNER)
            sum(range(300_000_000))
    except KeyboardInterrupt:
        child._EXIT(0)
    child._EXIT(3)


@pytest.mark.usefixtures("deadline_fires_in_a_child")
def test_an_owned_ctrl_c_after_an_alarm_held_in_pyct_s_frames_reaches_the_caller() -> None:
    pid = os.fork()
    if pid == 0:
        ctrl_c_after_an_alarm_held_in_pyct_s_frames()
    _, status = os.waitpid(pid, 0)

    assert os.waitstatus_to_exitcode(status) == 0


def hang_while_the_caller_handles_a_ctrl_c() -> None:
    started = time.monotonic()
    try:
        raise KeyboardInterrupt
    except KeyboardInterrupt:
        try:
            with deadline(started + 0.05):
                spin_until(started + 2)
        except DeadlineError:
            child._EXIT(0 if time.monotonic() - started < 0.3 else 2)
    child._EXIT(1)


@pytest.mark.usefixtures("deadline_fires_in_a_child")
def test_an_owned_ctrl_c_handled_before_the_block_holds_no_alarm_back() -> None:
    assert settled_then(hang_while_the_caller_handles_a_ctrl_c) == 0

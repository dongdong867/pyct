"""The deadline in a process pyct does not own, as pyct's process with ``--in-process``.

Its SIGALRM comes from a watcher thread, and the process's own handler comes
back after each block. The input's own process, which owns SIGALRM, is tested
where it is settled, in ``tests/unit/run/test_child.py``.
"""

import asyncio
import json
import os
import signal
import subprocess
import sys
import threading
import time
import types
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager

import pytest

from pyct.execution.deadline import DeadlineError, deadline
from tests.acceptance.harness import COVERAGE_STARTUP, REPO_ROOT
from tests.unit.deadline_fires import DEADLINE_FIRES
from tests.unit.execution.ctrl_c_in_c import interrupted_call


@pytest.fixture
def counting() -> Iterator[list[int]]:
    """A SIGALRM handler of the test's own, which counts its calls, restored after the test."""
    calls: list[int] = []
    previous = signal.signal(signal.SIGALRM, lambda number, frame: calls.append(number))
    yield calls
    signal.signal(signal.SIGALRM, previous)


@DEADLINE_FIRES
def test_deadline_stops_a_loop_that_never_ends() -> None:
    with pytest.raises(DeadlineError), deadline(time.monotonic() + 0.05):
        while True:
            pass


@DEADLINE_FIRES
def test_deadline_fires_at_once_when_the_instant_has_passed() -> None:
    with pytest.raises(DeadlineError), deadline(time.monotonic() - 1):
        while True:
            pass


@DEADLINE_FIRES
def test_deadline_stops_a_sleep() -> None:
    started = time.monotonic()

    with pytest.raises(DeadlineError), deadline(started + 0.05):
        time.sleep(5)

    assert time.monotonic() - started < 1


def test_no_deadline_installs_nothing() -> None:
    before = signal.getsignal(signal.SIGALRM)
    threads = threading.active_count()

    with deadline(None):
        inside = signal.getsignal(signal.SIGALRM)
        running = threading.active_count()

    assert inside is before
    assert running == threads


def test_deadline_restores_the_previous_handler_and_leaves_no_thread() -> None:
    before = signal.getsignal(signal.SIGALRM)
    threads = threading.active_count()

    with deadline(time.monotonic() + 10):
        pass

    assert signal.getsignal(signal.SIGALRM) is before
    assert threading.active_count() == threads


def test_deadline_sets_no_timer() -> None:
    with deadline(time.monotonic() + 10):
        armed = signal.getitimer(signal.ITIMER_REAL)

    # the process's one real-time timer stays free for the caller's own use
    assert armed == (0.0, 0.0)


def test_a_signal_sent_as_the_block_ends_never_reaches_the_previous_handler(
    counting: list[int],
) -> None:
    before = signal.getsignal(signal.SIGALRM)
    held = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGALRM})
    try:
        with deadline(time.monotonic() + 0.01):
            # the alarm is sent while this thread holds it, so it is still on its way as the
            # block ends
            waited = time.monotonic() + 5
            while signal.SIGALRM not in signal.sigpending() and time.monotonic() < waited:
                time.sleep(0.001)
            pending = signal.SIGALRM in signal.sigpending()
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, held)
    # a signal let through here would run the handler at this call
    time.sleep(0)

    assert pending
    assert counting == []
    assert signal.getsignal(signal.SIGALRM) is before


@DEADLINE_FIRES
def test_an_alarm_that_lands_on_a_ctrl_c_leaves_it_to_go_on(counting: list[int]) -> None:
    with pytest.raises(KeyboardInterrupt), deadline(time.monotonic() + 10):
        try:
            raise KeyboardInterrupt
        except KeyboardInterrupt:
            # the alarm lands while the Ctrl-C is on its way out of the target
            signal.pthread_kill(threading.get_ident(), signal.SIGALRM)
            raise

    assert counting == []


@DEADLINE_FIRES
def test_an_alarm_that_lands_as_the_way_out_begins_lets_it_finish(counting: list[int]) -> None:
    before = signal.getsignal(signal.SIGALRM)
    threads = threading.active_count()
    guard = deadline(time.monotonic() + 10)
    way_out = type(guard).__exit__.__code__

    def land(frame: types.FrameType, event: str, arg: object) -> None:
        if event == "call" and frame.f_code is way_out:
            signal.pthread_kill(threading.get_ident(), signal.SIGALRM)

    previous = sys.gettrace()
    sys.settrace(land)
    try:
        with guard:
            pass
    finally:
        sys.settrace(previous)

    assert signal.getsignal(signal.SIGALRM) is before
    assert counting == []
    assert threading.active_count() == threads


def call_under(guard: AbstractContextManager[None]) -> None:
    """A call under a deadline, held by a frame of its own, as pyct's call of the target is."""
    with guard:
        pass


@DEADLINE_FIRES
def test_an_alarm_after_a_way_out_a_ctrl_c_cut_short_ends_no_later_call() -> None:
    before = signal.getsignal(signal.SIGALRM)
    guard = deadline(time.monotonic() + 0.05)
    way_out = type(guard).__exit__.__code__

    def interrupt(frame: types.FrameType, event: str, arg: object) -> None:
        if event == "call" and frame.f_code is way_out:
            raise KeyboardInterrupt

    previous = sys.gettrace()
    sys.settrace(interrupt)
    try:
        with pytest.raises(KeyboardInterrupt):
            call_under(guard)
    finally:
        sys.settrace(previous)
    try:
        # the next call's block spans the instant the first one's watcher sends at
        with deadline(time.monotonic() + 10):
            time.sleep(0.2)
    finally:
        signal.signal(signal.SIGALRM, before)


def test_a_ctrl_c_as_the_handler_goes_back_still_lets_it_go_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = signal.getsignal(signal.SIGALRM)
    threads = threading.active_count()
    swap = signal.signal
    interrupted: list[bool] = []

    def interrupt_once(number: int, handler: object) -> object:
        if number == signal.SIGALRM and handler is before and not interrupted:
            interrupted.append(True)
            # a Ctrl-C's handler, run by signal.signal before it swaps, raises
            raise KeyboardInterrupt
        return swap(number, handler)  # pyrefly: ignore[bad-argument-type]

    monkeypatch.setattr(signal, "signal", interrupt_once)

    with pytest.raises(KeyboardInterrupt), deadline(time.monotonic() + 10):
        pass

    assert interrupted
    assert signal.getsignal(signal.SIGALRM) is before
    # the watcher ended with the block, not at its instant
    assert threading.active_count() == threads


def ctrl_c_as_the_watcher_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Send the main thread a Ctrl-C from a new thread, while the main one waits for it to start."""
    real = threading.Thread._bootstrap_inner  # pyrefly: ignore[missing-attribute]
    main = threading.get_ident()

    def interrupted(thread: threading.Thread) -> None:
        signal.pthread_kill(main, signal.SIGINT)
        time.sleep(0.05)
        real(thread)

    monkeypatch.setattr(threading.Thread, "_bootstrap_inner", interrupted)


def ctrl_c_as_the_watcher_ends(monkeypatch: pytest.MonkeyPatch) -> None:
    """Send the main thread a Ctrl-C as it begins to wait for a thread to end."""
    real = threading.Thread.join
    main = threading.get_ident()

    def interrupted(thread: threading.Thread, timeout: float | None = None) -> None:
        signal.pthread_kill(main, signal.SIGINT)
        real(thread, timeout)

    monkeypatch.setattr(threading.Thread, "join", interrupted)


@pytest.mark.parametrize("when", [ctrl_c_as_the_watcher_starts, ctrl_c_as_the_watcher_ends])
def test_a_ctrl_c_as_the_watcher_starts_or_ends_comes_once_all_is_undone(
    monkeypatch: pytest.MonkeyPatch, when: Callable[[pytest.MonkeyPatch], None]
) -> None:
    before = signal.getsignal(signal.SIGALRM)
    threads = threading.active_count()
    when(monkeypatch)

    # a KeyboardInterrupt, not the RuntimeError a Ctrl-C inside the thread's start makes
    with pytest.raises(KeyboardInterrupt), deadline(time.monotonic() + 10):
        pass

    assert signal.getsignal(signal.SIGALRM) is before
    assert threading.active_count() == threads


def test_blocks_that_end_as_their_alarm_comes_keep_it_inside() -> None:
    env = {k: v for k, v in os.environ.items() if k not in COVERAGE_STARTUP}
    stressed = {
        (handler, where): subprocess.Popen(
            [sys.executable, "-m", "tests.unit.execution.deadline_stress", handler, where, "5"],
            cwd=REPO_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for handler in ("default", "counting")
        for where in ("owned", "borrowed")
    }

    for case, process in stressed.items():
        stdout, stderr = process.communicate(timeout=60)
        # SIG_DFL would have ended the process by SIGALRM
        assert process.returncode == 0, (case, process.returncode, stderr)
        tally = json.loads(stdout)
        assert tally["escaped"] == 0, (case, tally)
        assert tally["calls"] == 0, (case, tally)


@DEADLINE_FIRES
def test_an_alarm_that_lands_on_a_target_s_own_base_exception_still_stops_it() -> None:
    started = time.monotonic()

    with pytest.raises(DeadlineError), deadline(started + 0.05):
        try:
            raise asyncio.CancelledError
        except asyncio.CancelledError:
            # the alarm lands while the target handles its own cancel, then it hangs
            while time.monotonic() < started + 0.15:
                pass
        # a hang, bounded so the test fails rather than waits when no alarm comes
        while time.monotonic() < started + 2:
            pass

    assert time.monotonic() - started < 1


@DEADLINE_FIRES
def test_an_alarm_held_back_by_a_ctrl_c_comes_once_it_is_caught() -> None:
    started = time.monotonic()

    with pytest.raises(DeadlineError), deadline(started + 0.05):
        try:
            raise KeyboardInterrupt
        except KeyboardInterrupt:
            while time.monotonic() < started + 0.15:
                pass
        # a hang, bounded so the test fails rather than waits when no alarm comes
        while time.monotonic() < started + 2:
            pass

    assert time.monotonic() - started < 1


@DEADLINE_FIRES
def test_an_alarm_held_back_by_a_ctrl_c_that_never_leaves_comes_after_a_bound() -> None:
    started = time.monotonic()

    with pytest.raises(DeadlineError), deadline(started + 0.05):
        try:
            raise KeyboardInterrupt
        except KeyboardInterrupt:
            # a handler that never returns, bounded so the test fails rather than waits
            while time.monotonic() < started + 3:
                pass

    took = time.monotonic() - started
    assert 0.5 <= took < 1.5, took


@DEADLINE_FIRES
@pytest.mark.parametrize("name", ["total", "total_then_finally"])
def test_a_ctrl_c_during_a_c_call_that_outlives_the_deadline_reaches_the_caller(name: str) -> None:
    with pytest.raises(KeyboardInterrupt):
        interrupted_call(name)

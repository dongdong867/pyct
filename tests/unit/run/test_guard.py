"""The guard, which ends pyct's process when pyct's own handler cannot.

This test plays the watcher: it forks a stand-in for pyct's process, starts the guard as a
child of its own on the lifeline, and holds the lifeline's write end. The stand-in never
returns into the test runner: it ends its process on every path.
"""

import contextlib
import os
import signal
import time
from collections.abc import Callable, Generator

import pytest

from pyct.run.guard import STOP_GRACE, guard
from pyct.run.process import Child, Waited


def stand_in(on_sigterm: int | Callable[[int, object], None]) -> int:
    """A process that waits, taking a SIGTERM as ``on_sigterm`` says, once it is ready.

    At its default action, or ignored, as a process whose handler cannot run
    takes it.
    """
    ready, running = os.pipe()
    pid = os.fork()
    if pid == 0:
        try:
            signal.signal(signal.SIGTERM, on_sigterm)
            os.write(running, b"!")
            time.sleep(10)
        finally:
            os._exit(0)
    os.close(running)
    os.read(ready, 1)
    os.close(ready)
    return pid


@contextlib.contextmanager
def guarding(target: int) -> Generator[tuple[Child, int]]:
    """The guard of ``target``, and the lifeline's write end; both are ended on the way out."""
    lifeline, kept = os.pipe()
    started = guard(lifeline, target)
    os.close(lifeline)
    try:
        assert started is not None
        yield started, kept
    finally:
        with contextlib.suppress(OSError):
            os.close(kept)
        if started is not None:
            started.end()


def ended(pid: int) -> tuple[Waited, float]:
    """How the stand-in ended, and how long after this call."""
    started = time.monotonic()
    _, status = os.waitpid(pid, 0)
    return Waited.of(status), time.monotonic() - started


def test_a_sigterm_the_watcher_passed_on_ends_by_sigkill_after_the_grace() -> None:
    # the stand-in cannot act on the SIGTERM, as in one long call in C
    pid = stand_in(signal.SIG_IGN)
    with guarding(pid) as (_, kept):
        os.write(kept, b"!")
        waited, took = ended(pid)

    assert waited.signal == signal.SIGKILL
    assert STOP_GRACE <= took < STOP_GRACE + 1


def test_the_watcher_gone_has_the_guard_send_the_sigterm_itself() -> None:
    pid = stand_in(signal.SIG_DFL)
    with guarding(pid) as (_, kept):
        os.close(kept)
        waited, took = ended(pid)

    assert waited.signal == signal.SIGTERM
    assert took < STOP_GRACE


def test_the_watcher_gone_ends_a_process_that_cannot_act_on_its_sigterm() -> None:
    pid = stand_in(signal.SIG_IGN)
    with guarding(pid) as (_, kept):
        os.close(kept)
        waited, took = ended(pid)

    assert waited.signal == signal.SIGKILL
    assert STOP_GRACE <= took < STOP_GRACE + 1


def test_the_guard_signals_no_pid_that_names_no_process() -> None:
    # pyct's process, ended and reaped, has given its pid up
    gone = os.fork()
    if gone == 0:
        os._exit(0)
    os.waitpid(gone, 0)
    with guarding(gone) as (started, kept):
        os.close(kept)
        waited = started.wait()

    assert waited == Waited(signal=None, code=0)


def test_the_guard_runs_in_a_process_group_of_its_own() -> None:
    with guarding(os.getpid()) as (started, _):
        # a Ctrl-C from the terminal signals pyct's group, and this is not it
        assert os.getpgid(started.pid) == started.pid
        assert os.getpgid(started.pid) != os.getpgrp()


def test_a_guard_that_cannot_start_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    def refused(*args: object, **kwargs: object) -> int:
        raise BlockingIOError(35, "Resource temporarily unavailable")

    monkeypatch.setattr(os, "posix_spawn", refused)
    lifeline, kept = os.pipe()
    try:
        assert guard(lifeline, os.getpid()) is None
    finally:
        os.close(lifeline)
        os.close(kept)

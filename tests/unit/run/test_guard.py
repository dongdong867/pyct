"""The guard, which ends pyct's process when pyct's own handler cannot.

Each test forks a stand-in for pyct's process, which starts its guard and then waits, and
plays the watcher itself by holding the lifeline's write end. The stand-in never returns
into the test runner: it ends its process on every path.
"""

import os
import signal
import time
from collections.abc import Callable

import pytest

from pyct.run.guard import STOP_GRACE, guard
from pyct.run.process import Waited


def guarded(on_sigterm: int | Callable[[int, object], None]) -> tuple[int, int]:
    """A stand-in for pyct's process, with its guard, and the lifeline's write end.

    ``on_sigterm`` is how the stand-in takes a SIGTERM: at its default
    action, or ignored, as a process whose handler cannot run takes it.
    """
    lifeline, kept = os.pipe()
    ready, running = os.pipe()
    pid = os.fork()
    if pid == 0:
        try:
            signal.signal(signal.SIGTERM, on_sigterm)
            os.close(kept)
            guard(lifeline)
            os.close(lifeline)
            os.write(running, b"!")
            time.sleep(10)
        finally:
            os._exit(0)
    os.close(lifeline)
    os.close(running)
    os.read(ready, 1)
    os.close(ready)
    return pid, kept


def ended(pid: int) -> tuple[Waited, float]:
    """How the stand-in ended, and how long after this call."""
    started = time.monotonic()
    _, status = os.waitpid(pid, 0)
    return Waited.of(status), time.monotonic() - started


def test_a_sigterm_the_watcher_passed_on_ends_by_sigkill_after_the_grace() -> None:
    # the stand-in cannot act on the SIGTERM, as in one long call in C
    pid, kept = guarded(signal.SIG_IGN)
    os.write(kept, b"!")

    waited, took = ended(pid)
    os.close(kept)

    assert waited.signal == signal.SIGKILL
    assert STOP_GRACE <= took < STOP_GRACE + 1


def test_the_watcher_gone_has_the_guard_send_the_sigterm_itself() -> None:
    pid, kept = guarded(signal.SIG_DFL)
    os.close(kept)

    waited, took = ended(pid)

    assert waited.signal == signal.SIGTERM
    assert took < STOP_GRACE


def test_the_watcher_gone_ends_a_process_that_cannot_act_on_its_sigterm() -> None:
    pid, kept = guarded(signal.SIG_IGN)
    os.close(kept)

    waited, took = ended(pid)

    assert waited.signal == signal.SIGKILL
    assert STOP_GRACE <= took < STOP_GRACE + 1


def test_the_guard_leaves_alone_a_process_that_is_not_its_parent() -> None:
    # the pid the guard was given belongs to a process that is not its parent, as a pid does
    # once pyct's process has ended and the system gave it to another
    other = os.fork()
    if other == 0:
        time.sleep(10)
        os._exit(0)
    lifeline, kept = os.pipe()
    started = guard(lifeline, parent=other)
    os.close(lifeline)
    assert started is not None
    try:
        os.close(kept)
        waited = started.wait()

        assert waited == Waited(signal=None, code=0)
        assert os.waitpid(other, os.WNOHANG) == (0, 0)
    finally:
        os.kill(other, signal.SIGKILL)
        os.waitpid(other, 0)


def test_the_guard_runs_in_a_process_group_of_its_own() -> None:
    lifeline, kept = os.pipe()
    started = guard(lifeline, parent=os.getpid())
    os.close(lifeline)
    assert started is not None
    try:
        # a Ctrl-C from the terminal signals pyct's group, and this is not it
        assert os.getpgid(started.pid) == started.pid
        assert os.getpgid(started.pid) != os.getpgrp()
    finally:
        started.end()
        os.close(kept)


def test_a_guard_that_cannot_start_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    def refused(*args: object, **kwargs: object) -> int:
        raise BlockingIOError(35, "Resource temporarily unavailable")

    monkeypatch.setattr(os, "posix_spawn", refused)
    lifeline, kept = os.pipe()
    try:
        assert guard(lifeline) is None
    finally:
        os.close(lifeline)
        os.close(kept)

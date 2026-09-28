"""How pyct's process waits for an input's process: by the system's notice of its exit.

It sets no timer and takes no signal while it waits, so nothing lands in
pyct's own code after the wait.
"""

import contextlib
import errno
import os
import select
import signal
import time
from collections.abc import Callable, Generator

import pytest

from pyct.run import exits
from pyct.run.process import KILL_GRACE, Waited, watched
from tests.unit.run.test_process import sleeper


def test_pyct_s_process_waits_with_no_alarm_of_its_own(monkeypatch: pytest.MonkeyPatch) -> None:
    touched: list[str] = []
    set_timer, set_handler = signal.setitimer, signal.signal

    def timer(which: int, seconds: float, interval: float = 0.0) -> tuple[float, float]:
        touched.append("setitimer")
        return set_timer(which, seconds, interval)

    def handler(number: int, action: object) -> object:
        if number == signal.SIGALRM:
            touched.append("SIGALRM handler")
        return set_handler(number, action)  # pyrefly: ignore[bad-argument-type]

    monkeypatch.setattr(signal, "setitimer", timer)
    monkeypatch.setattr(signal, "signal", handler)

    waited = watched(lambda: sleeper(10), time.monotonic() + 0.05)

    assert waited == Waited(signal=signal.SIGKILL, code=None, killed=True)
    assert touched == []


def ended_before_the_wait() -> int:
    """A child that has exited, not yet reaped, by the time pyct starts to wait for it."""
    pid = sleeper(0)
    time.sleep(0.1)
    return pid


def test_a_process_that_ended_before_the_wait_is_read_at_once() -> None:
    started = time.monotonic()

    waited = watched(ended_before_the_wait, started + 5)

    assert waited == Waited(signal=None, code=0, killed=False)
    assert time.monotonic() - started < 1


@contextlib.contextmanager
def pidfds_only(monkeypatch: pytest.MonkeyPatch) -> Generator[Callable[[float], int]]:
    """A system without kqueue, whose exit notice is a pidfd, as Linux gives: ``sleeper`` for it.

    The pidfd stands in as a pipe whose write end only the child holds, so
    it reads as ready once the child has ended, as a pidfd does.
    """
    monkeypatch.delattr(select, "kqueue", raising=False)
    notices: dict[int, int] = {}
    monkeypatch.setattr(os, "pidfd_open", lambda pid: os.dup(notices[pid]), raising=False)

    def start(seconds: float) -> int:
        read, write = os.pipe()
        pid = sleeper(seconds)
        os.close(write)
        notices[pid] = read
        return pid

    try:
        yield start
    finally:
        for read in notices.values():
            os.close(read)


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0.0, Waited(signal=None, code=0, killed=False)),
        (10.0, Waited(signal=signal.SIGKILL, code=None, killed=True)),
    ],
    ids=["ends-before-the-kill", "runs-past-the-kill"],
)
def test_a_pidfd_says_when_the_process_ends(
    monkeypatch: pytest.MonkeyPatch, seconds: float, expected: Waited
) -> None:
    with pidfds_only(monkeypatch) as start:
        waited = watched(lambda: start(seconds), time.monotonic() + 0.05)

    assert waited == expected


class FailingQueue:
    """A kqueue whose notice is an error other than ESRCH, as a system short of memory gives."""

    def control(self, changes: object, most: int, timeout: float) -> list[select.kevent]:
        return [select.kevent(0, flags=select.KQ_EV_ERROR, data=errno.ENOMEM)]

    def close(self) -> None:
        pass


def test_a_kqueue_that_cannot_watch_the_process_raises_and_ends_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(select, "kqueue", FailingQueue)
    started: list[int] = []

    def start() -> int:
        started.append(sleeper(10))
        return started[0]

    with pytest.raises(OSError, match="memory"):
        watched(start, time.monotonic() + 5)

    # the process was killed and reaped on the way out
    with pytest.raises(ChildProcessError):
        os.waitpid(started[0], os.WNOHANG)


def refused(pid: int) -> int:
    """A pidfd_open the system refuses, as a kernel before 5.3 or a syscall filter does."""
    raise OSError(errno.ENOSYS, os.strerror(errno.ENOSYS))


def forbidden(pid: int) -> int:
    """A pidfd_open that fails for a reason other than a missing or refused call."""
    raise OSError(errno.EMFILE, os.strerror(errno.EMFILE))


@pytest.mark.parametrize("pidfd_open", [refused, None], ids=["refused", "missing"])
@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0.0, Waited(signal=None, code=0, killed=False)),
        (10.0, Waited(signal=signal.SIGKILL, code=None, killed=True)),
    ],
    ids=["ends-before-the-kill", "runs-past-the-kill"],
)
def test_a_system_with_no_exit_notice_is_asked_until_the_kill(
    monkeypatch: pytest.MonkeyPatch,
    pidfd_open: Callable[[int], int] | None,
    seconds: float,
    expected: Waited,
) -> None:
    monkeypatch.delattr(select, "kqueue", raising=False)
    if pidfd_open is None:
        monkeypatch.delattr(os, "pidfd_open", raising=False)
    else:
        monkeypatch.setattr(os, "pidfd_open", pidfd_open, raising=False)
    started = time.monotonic()

    waited = watched(lambda: sleeper(seconds), started + 0.1)

    assert waited == expected
    assert time.monotonic() - started < 1


def test_a_pidfd_that_fails_otherwise_raises_and_ends_the_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delattr(select, "kqueue", raising=False)
    monkeypatch.setattr(os, "pidfd_open", forbidden, raising=False)
    started: list[int] = []

    def start() -> int:
        started.append(sleeper(10))
        return started[0]

    with pytest.raises(OSError, match="files"):
        watched(start, time.monotonic() + 5)

    with pytest.raises(ChildProcessError):
        os.waitpid(started[0], os.WNOHANG)


def test_a_long_wait_waits_in_steps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(exits, "LONGEST_WAIT", 0.02)
    started = time.monotonic()

    waited = watched(lambda: sleeper(10), started + 0.1)

    took = time.monotonic() - started
    assert waited == Waited(signal=signal.SIGKILL, code=None, killed=True)
    assert 0.1 + KILL_GRACE <= took < 0.1 + KILL_GRACE + 0.5

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
from pyct.run.watch_page import WatchPage
from tests.acceptance.test_run_a_target_in_a_throwaway_process import is_running


def stand_in(on_sigterm: int | Callable[[int, object], None], page: WatchPage | None = None) -> int:
    """A process that waits, taking a SIGTERM as ``on_sigterm`` says, once it is ready.

    At its default action, or ignored, as a process whose handler cannot run
    takes it. With ``page``, it first starts an input's process of its own,
    which waits too, and names it on ``page``, as pyct's process does.
    """
    ready, running = os.pipe()
    pid = os.fork()
    if pid == 0:
        try:
            signal.signal(signal.SIGTERM, on_sigterm)
            if page is not None:
                page.name_input(waiting())
            os.write(running, b"!")
            time.sleep(10)
        finally:
            os._exit(0)
    os.close(running)
    os.read(ready, 1)
    os.close(ready)
    return pid


def waiting() -> int:
    """A child of this process that waits, as an input's process does; its pid."""
    pid = os.fork()
    if pid == 0:
        try:
            time.sleep(10)
        finally:
            os._exit(0)
    return pid


@pytest.fixture
def page() -> Generator[WatchPage]:
    """A watcher's page, closed once the test ends."""
    made = WatchPage.for_command_line([])
    yield made
    made.close()


@contextlib.contextmanager
def guarding(target: int, page: WatchPage | None = None) -> Generator[tuple[Child, int]]:
    """The guard of ``target``, reading ``page`` or a page of its own, and the lifeline's write
    end. On the way out the write end is closed, the guard ended and reaped, and a page of its
    own closed."""
    own = WatchPage.for_command_line([]) if page is None else None
    read = page or own
    assert read is not None
    lifeline, kept = os.pipe()
    started = guard(lifeline, target, read.fd)
    os.close(lifeline)
    try:
        assert started is not None
        yield started, kept
    finally:
        with contextlib.suppress(OSError):
            os.close(kept)
        if started is not None:
            started.end()
        if own is not None:
            own.close()


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


# pyct's process held past the grace, as a lock or a slow host holds it: the guard ends the input
# its page names too, whether the watcher passed a SIGTERM on or is gone
@pytest.mark.parametrize("watcher_gone", [False, True], ids=["sigterm-passed-on", "watcher-gone"])
def test_the_guard_ends_the_input_the_page_names_with_pyct_s_process(
    watcher_gone: bool, page: WatchPage
) -> None:
    pid = stand_in(signal.SIG_IGN, page)
    named = page.input()
    assert named is not None
    try:
        with guarding(pid, page) as (_, kept):
            if watcher_gone:
                os.close(kept)
            else:
                os.write(kept, b"!")
            waited, _ = ended(pid)

        assert waited.signal == signal.SIGKILL
        assert not is_running(named)
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.kill(named, signal.SIGKILL)


# a pid the page names that is not pyct's child, as one pyct reaped and the system handed out
# again, or one the system reaped for a target that ignores SIGCHLD, gets no signal
def test_the_guard_leaves_a_named_pid_that_is_not_pyct_s_child_alone(page: WatchPage) -> None:
    sibling = waiting()
    page.name_input(sibling)
    pid = stand_in(signal.SIG_IGN)
    try:
        with guarding(pid, page) as (_, kept):
            os.write(kept, b"!")
            waited, _ = ended(pid)

        assert waited.signal == signal.SIGKILL
        assert os.waitpid(sibling, os.WNOHANG) == (0, 0)
    finally:
        Child(sibling).end()


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
        began = time.monotonic()
        os.close(kept)
        waited = started.wait()
        took = time.monotonic() - began

    assert waited == Waited(signal=None, code=0)
    # a guard that found the pid gone ends at once, rather than wait out the grace
    assert took < STOP_GRACE / 2


def test_the_guard_runs_in_a_process_group_of_its_own() -> None:
    with guarding(os.getpid()) as (started, _):
        # a Ctrl-C from the terminal signals pyct's group, and this is not it
        assert os.getpgid(started.pid) == started.pid
        assert os.getpgid(started.pid) != os.getpgrp()


def test_a_guard_that_cannot_start_is_none(
    monkeypatch: pytest.MonkeyPatch, page: WatchPage
) -> None:
    def refused(*args: object, **kwargs: object) -> int:
        raise BlockingIOError(35, "Resource temporarily unavailable")

    monkeypatch.setattr(os, "posix_spawn", refused)
    lifeline, kept = os.pipe()
    try:
        assert guard(lifeline, os.getpid(), page.fd) is None
    finally:
        os.close(lifeline)
        os.close(kept)

"""How pyct reads the end of an input's process: the rules, the raw status, the reaping."""

import contextlib
import dataclasses
import functools
import os
import select
import signal
import threading
import time
from collections.abc import Callable, Generator

import pytest

from pyct.core.branch import Branch, Site
from pyct.results.failure import Failure, FailureKind
from pyct.results.record import DowngradeCount
from pyct.run.journal import Reading
from pyct.run.process import KILL_GRACE, Waited, _Child, ending, watched

FORK = Branch(expression=["<", "x", 10], taken=True, site=Site(file="t.py", line=2, col=7))
RAISED = Failure(kind=FailureKind.TARGET_RAISED, detail="ValueError: x")
FACTS = Reading(
    lines=frozenset({2, 3}),
    branches=(FORK,),
    downgrades=(DowngradeCount(name="__abs__", count=2),),
    started=True,
)
NOT_ENDED = FACTS
ENDED = dataclasses.replace(FACTS, ended=True, end=RAISED)
RETURNED = dataclasses.replace(FACTS, ended=True, end=None)
INCOMPLETE = dataclasses.replace(FACTS, problem="the journal is full")
NOT_STARTED = dataclasses.replace(FACTS, started=False)
EXITED = Waited(signal=None, code=0)
SEGFAULTED = Waited(signal=signal.SIGSEGV, code=None)
KILLED = Waited(signal=signal.SIGKILL, code=None, killed=True)


@pytest.mark.parametrize(
    ("reading", "waited", "failure"),
    [
        pytest.param(
            INCOMPLETE,
            EXITED,
            Failure(kind=FailureKind.PYCT_BUG, detail="the journal is full"),
            id="incomplete-facts-beat-everything",
        ),
        pytest.param(ENDED, KILLED, RAISED, id="the-calls-own-ending-beats-a-late-kill"),
        pytest.param(RETURNED, SEGFAULTED, None, id="a-call-that-returned-returned"),
        pytest.param(
            NOT_ENDED,
            KILLED,
            Failure(kind=FailureKind.TIMEOUT, detail="deadline passed"),
            id="killed-by-pyct",
        ),
        pytest.param(
            NOT_ENDED,
            SEGFAULTED,
            Failure(kind=FailureKind.CRASHED, detail="killed by SIGSEGV"),
            id="killed-by-a-signal",
        ),
        pytest.param(
            NOT_ENDED,
            Waited(signal=99, code=None),
            Failure(kind=FailureKind.CRASHED, detail="killed by signal 99"),
            id="a-signal-python-names-no-name",
        ),
        pytest.param(
            NOT_ENDED,
            Waited(signal=None, code=3),
            Failure(kind=FailureKind.SYSTEM_EXIT, detail="exited with code 3"),
            id="exited",
        ),
        pytest.param(
            NOT_STARTED,
            Waited(signal=None, code=1),
            Failure(
                kind=FailureKind.PYCT_BUG,
                detail="the input's process ended before its call began: exited with code 1",
            ),
            id="exited-before-the-call-began",
        ),
        pytest.param(
            NOT_STARTED,
            SEGFAULTED,
            Failure(
                kind=FailureKind.PYCT_BUG,
                detail="the input's process ended before its call began: killed by SIGSEGV",
            ),
            id="killed-before-the-call-began",
        ),
        pytest.param(
            NOT_STARTED,
            KILLED,
            Failure(kind=FailureKind.TIMEOUT, detail="deadline passed"),
            id="killed-by-pyct-before-the-call-began",
        ),
    ],
)
def test_the_first_rule_that_holds_says_how_the_input_ended(
    reading: Reading, waited: Waited, failure: Failure | None
) -> None:
    result = ending(reading, waited)

    assert result.failure == failure
    # the facts the process wrote stay, however it ended
    assert result.lines == FACTS.lines
    assert result.branches == FACTS.branches
    assert result.downgrades == FACTS.downgrades


def test_a_status_says_the_exit_code_or_the_signal() -> None:
    exited = os.fork()
    if exited == 0:
        os._exit(3)
    signaled = os.fork()
    if signaled == 0:
        os.kill(os.getpid(), signal.SIGTERM)
        time.sleep(10)
        os._exit(0)

    assert Waited.of(os.waitpid(exited, 0)[1]) == Waited(signal=None, code=3)
    assert Waited.of(os.waitpid(signaled, 0)[1]) == Waited(signal=signal.SIGTERM, code=None)


def test_ending_a_process_that_still_runs_kills_and_reaps_it() -> None:
    pid = os.fork()
    if pid == 0:
        time.sleep(10)
        os._exit(0)
    child = _Child(pid)

    child.end()

    assert child.status is not None
    assert Waited.of(child.status).signal == signal.SIGKILL
    with pytest.raises(ChildProcessError):
        os.waitpid(pid, os.WNOHANG)


def test_ending_a_process_already_reaped_leaves_its_pid_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pid = os.fork()
    if pid == 0:
        os._exit(0)
    os.waitpid(pid, 0)
    killed: list[int] = []
    monkeypatch.setattr(os, "kill", lambda pid, sig: killed.append(pid))
    child = _Child(pid)

    # reaped by pyct, the status lost on the way out: the pid may be another process's now
    child.end()

    assert killed == []


def sleeper(seconds: float) -> int:
    """A child that sleeps, then exits 0: the pid, for ``watched`` to wait on."""
    pid = os.fork()
    if pid == 0:
        time.sleep(seconds)
        os._exit(0)
    return pid


def test_a_process_past_the_deadline_is_killed_after_the_grace() -> None:
    started = time.monotonic()

    waited = watched(lambda: sleeper(10), started + 0.1)

    took = time.monotonic() - started
    assert waited == Waited(signal=signal.SIGKILL, code=None, killed=True)
    assert 0.1 + KILL_GRACE <= took < 0.1 + KILL_GRACE + 0.5


def test_a_process_that_ends_before_the_deadline_is_left_to_end() -> None:
    waited = watched(lambda: sleeper(0), time.monotonic() + 5)

    assert waited == Waited(signal=None, code=0, killed=False)
    # the kill timer is gone with the process
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)


def test_with_no_deadline_pyct_waits_as_long_as_the_process_runs() -> None:
    waited = watched(lambda: sleeper(0.2), None)

    assert waited == Waited(signal=None, code=0, killed=False)


def test_a_ctrl_c_as_the_process_starts_still_ends_it() -> None:
    started: list[int] = []

    def start_then_interrupt() -> int:
        pid = sleeper(10)
        started.append(pid)
        # a Ctrl-C landing after the process exists, before pyct holds its pid. Aimed at this
        # thread, the one pyct waits in, as the only thread of a process pyct forks from
        signal.pthread_kill(threading.get_ident(), signal.SIGINT)
        return pid

    with pytest.raises(KeyboardInterrupt):
        watched(start_then_interrupt, None)

    # the process was killed and reaped on the way out, so no pid of it is left to wait for
    with pytest.raises(ChildProcessError):
        os.waitpid(started[0], os.WNOHANG)


def says_it_runs(running: int, started: list[int]) -> int:
    """A child that writes to ``running`` once it runs, then sleeps; its pid goes in ``started``."""
    pid = os.fork()
    if pid == 0:
        os.write(running, b"!")
        time.sleep(10)
        os._exit(0)
    started.append(pid)
    return pid


def interrupt_once_it_runs(ready: int, waiting: int) -> None:
    """SIGINT the thread ``waiting`` once the child says on ``ready`` that it runs."""
    os.read(ready, 1)
    signal.pthread_kill(waiting, signal.SIGINT)


@contextlib.contextmanager
def interrupted_once_running(started: list[int]) -> Generator[Callable[[], int]]:
    """A start for ``watched`` whose process, once it runs, gets pyct's waiting thread a SIGINT.

    Only pyct's process is interrupted, in the thread that waits, as by a
    kill aimed at pyct alone.
    """
    ready, running = os.pipe()
    waiting = threading.get_ident()
    interrupter = threading.Thread(target=interrupt_once_it_runs, args=(ready, waiting))
    interrupter.start()
    try:
        yield functools.partial(says_it_runs, running, started)
    finally:
        interrupter.join()
        os.close(ready)
        os.close(running)


def test_a_ctrl_c_while_pyct_waits_ends_the_process_and_goes_on() -> None:
    started: list[int] = []

    with interrupted_once_running(started) as start, pytest.raises(KeyboardInterrupt):
        watched(start, None)

    with pytest.raises(ChildProcessError):
        os.waitpid(started[0], os.WNOHANG)


def exited() -> int:
    """A child that has exited and is not reaped yet: a zombie whose status waits for pyct."""
    pid = os.fork()
    if pid == 0:
        os._exit(4)
    ended_unreaped(pid)
    return pid


def ended_unreaped(pid: int) -> None:
    """Wait until ``pid`` has ended, leaving its status for a later wait to reap."""
    if hasattr(os, "waitid"):
        os.waitid(os.P_PID, pid, os.WEXITED | os.WNOWAIT)
        return
    queue = select.kqueue()
    ends = select.kevent(
        pid,
        filter=select.KQ_FILTER_PROC,
        flags=select.KQ_EV_ADD | select.KQ_EV_ONESHOT,
        fflags=select.KQ_NOTE_EXIT,
    )
    try:
        assert queue.control([ends], 1, 10.0), f"process {pid} did not end"
    except ProcessLookupError:
        # it ended before the watch was set up
        pass
    finally:
        queue.close()


def test_a_process_the_kill_timer_found_ended_is_read_from_what_it_kept() -> None:
    child = _Child(exited())

    # the timer fires after the process ended and before the wait reaped it
    child.kill_if_running()
    waited = child.wait()

    assert waited == Waited(signal=None, code=4, killed=False)


def test_the_kill_timer_leaves_a_process_it_already_read_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    child = _Child(exited())
    child.kill_if_running()
    killed: list[int] = []
    monkeypatch.setattr(os, "kill", lambda pid, sig: killed.append(pid))

    child.kill_if_running()

    assert killed == []


def test_the_kill_timer_leaves_a_process_the_wait_reaped_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pid = exited()
    os.waitpid(pid, 0)
    killed: list[int] = []
    monkeypatch.setattr(os, "kill", lambda pid, sig: killed.append(pid))

    # the wait reaped it, and the timer fired before the status was kept
    _Child(pid).kill_if_running()

    assert killed == []


def test_a_wait_on_a_process_no_one_kept_the_status_of_raises() -> None:
    pid = exited()
    os.waitpid(pid, 0)

    with pytest.raises(ChildProcessError):
        _Child(pid).wait()


def test_ending_a_process_that_exited_reaps_it_without_a_kill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    child = _Child(exited())
    killed: list[int] = []
    monkeypatch.setattr(os, "kill", lambda pid, sig: killed.append(pid))

    child.end()

    assert killed == []
    assert child.status is not None
    assert Waited.of(child.status) == Waited(signal=None, code=4)


def test_a_second_ctrl_c_as_pyct_ends_the_process_still_reaps_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pid = sleeper(10)
    real_kill = os.kill

    def kill_then_interrupt(target: int, sig: int) -> None:
        real_kill(target, sig)
        # a second Ctrl-C, landing between the kill and the reap
        signal.pthread_kill(threading.get_ident(), signal.SIGINT)

    monkeypatch.setattr(os, "kill", kill_then_interrupt)

    with pytest.raises(KeyboardInterrupt):
        _Child(pid).end()

    with pytest.raises(ChildProcessError):
        os.waitpid(pid, os.WNOHANG)

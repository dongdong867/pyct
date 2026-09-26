"""How pyct reads the end of an input's process: the rules, the raw status, the reaping."""

import os
import signal
import time

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
)
NOT_ENDED = FACTS
ENDED = Reading(FACTS.lines, FACTS.branches, FACTS.downgrades, ended=True, end=RAISED)
RETURNED = Reading(FACTS.lines, FACTS.branches, FACTS.downgrades, ended=True, end=None)
INCOMPLETE = Reading(FACTS.lines, FACTS.branches, FACTS.downgrades, problem="the journal is full")
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
        # a Ctrl-C landing after the process exists, before pyct holds its pid
        os.kill(os.getpid(), signal.SIGINT)
        return pid

    with pytest.raises(KeyboardInterrupt):
        watched(start_then_interrupt, None)

    # the process was killed and reaped on the way out, so no pid of it is left to wait for
    with pytest.raises(ChildProcessError):
        os.waitpid(started[0], os.WNOHANG)


def test_a_ctrl_c_while_pyct_waits_ends_the_process_and_goes_on() -> None:
    started: list[int] = []

    def start() -> int:
        pid = os.fork()
        if pid == 0:
            # only pyct's process is interrupted, as by a kill aimed at it alone
            os.kill(os.getppid(), signal.SIGINT)
            time.sleep(10)
            os._exit(0)
        started.append(pid)
        return pid

    with pytest.raises(KeyboardInterrupt):
        watched(start, None)

    with pytest.raises(ChildProcessError):
        os.waitpid(started[0], os.WNOHANG)

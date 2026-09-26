"""One input's process as pyct's own process sees it: started, waited for, and how it ended.

pyct reads only what the system reports about the process, whether its
call finished and wrote its ending, its exit code, and the signal that
ended it, named as Python's ``signal`` module names it, together with the
facts the process wrote to its journal. No rule here names a library or a
target.

At most one input's process exists at a time, and only inside one call of
``watched``, which never returns or raises while that process is left
unreaped: every way out kills it, if it still runs, and reaps it. pyct
kills a process only before reaping it, so the pid is still its own.

With a deadline, the process's own SIGALRM ends a Python hang at the
deadline, finally blocks included, so its line is the same as in pyct's
process. A call inside C, or a target that catches the alarm, never ends
that way, so pyct kills the process ``KILL_GRACE`` after the deadline.
pyct blocks in ``waitpid``; its own SIGALRM handler kills and does not
raise, so Python retries the wait, which then returns the killed
process's status. A handler that raised could land after the wait had
already reaped the process and lose its status.
"""

from __future__ import annotations

import contextlib
import os
import signal
from collections.abc import Callable, Generator
from dataclasses import dataclass

from pyct.execution.deadline import alarm
from pyct.execution.execute import ExecutionResult
from pyct.results.failure import Failure, FailureKind
from pyct.run.journal import Reading

# how long past the deadline an input's process may run before pyct kills it: long enough for
# the process's own alarm to end a Python hang, finally blocks included, even on a busy machine
KILL_GRACE = 0.5


class InputStartError(Exception):
    """pyct could not start a process for an input. The message is the system's reason."""


@dataclass(frozen=True)
class Waited:
    """How the input's process ended, as the system reported it, and whether pyct ended it.

    ``signal`` is the number of the signal that ended it, and ``code`` its
    exit code when it exited instead.
    """

    signal: int | None
    code: int | None
    killed: bool = False

    @classmethod
    def of(cls, status: int, *, killed: bool = False) -> Waited:
        """Read a raw ``waitpid`` status. This is the one place that reads one."""
        if os.WIFSIGNALED(status):
            return cls(signal=os.WTERMSIG(status), code=None, killed=killed)
        return cls(signal=None, code=os.WEXITSTATUS(status), killed=killed)


def watched(start: Callable[[], int], until: float | None) -> Waited:
    """Start the input's process with ``start``, which returns its pid, and wait for it to end.

    ``until`` is the input's deadline, a monotonic instant; the process is
    killed ``KILL_GRACE`` after it. ``None`` waits as long as it runs.

    A Ctrl-C is held from before the start until pyct holds the pid inside
    the guard that ends the process on the way out, so none lands between
    the two and leaves the process running. It then goes on, as
    KeyboardInterrupt, once the process is ended and reaped.
    """
    child: _Child | None = None
    try:
        # a Ctrl-C held here goes on as the block ends, with the process in the guard's hands
        with ctrl_c_held():
            child = _Child(start())
        with alarm(None if until is None else until + KILL_GRACE, child.kill_if_running):
            return child.wait()
    finally:
        if child is not None:
            child.end()


@contextlib.contextmanager
def ctrl_c_held() -> Generator[None]:
    """Hold a Ctrl-C until the block ends, then let it go on as it would have.

    The signal mask holds it for this thread, and a child forked inside the
    block starts with that mask. The system can still hand SIGINT to another
    thread of pyct's process, and Python then raises in this thread anyway,
    so a handler that only notes it holds it here too. On the way out the old
    handler comes back, and a noted Ctrl-C is raised again for it. Like the
    rest of ``run()``, this needs the main thread.
    """
    noted: list[int] = []
    previous = signal.signal(signal.SIGINT, lambda number, frame: noted.append(number))
    held = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT})
    try:
        yield
    finally:
        # unblocking runs the noting handler for a Ctrl-C this thread held
        signal.pthread_sigmask(signal.SIG_SETMASK, held)
        signal.signal(signal.SIGINT, signal.SIG_DFL if previous is None else previous)
        if noted:
            signal.raise_signal(signal.SIGINT)


class _Child:
    """One input's process, from its start until pyct has reaped it."""

    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.status: int | None = None
        self.killed = False

    def wait(self) -> Waited:
        """Wait for the process to end, and read how it did."""
        try:
            _, status = os.waitpid(self.pid, 0)
        except ChildProcessError:
            # the kill timer found the process ended and reaped it first
            if self.status is None:
                raise
            status = self.status
        self.status = status
        return Waited.of(status, killed=self.killed)

    def kill_if_running(self, *_: object) -> None:
        """Kill the process unless it has ended. The kill timer's handler: it never raises.

        The status is asked for without waiting first. A process that ended
        is reaped here and its status kept for ``wait``; one ``wait`` already
        reaped is left alone.
        """
        if self.status is not None:
            return
        try:
            pid, status = os.waitpid(self.pid, os.WNOHANG)
        except ChildProcessError:
            return
        if pid != 0:
            self.status = status
            return
        os.kill(self.pid, signal.SIGKILL)
        self.killed = True

    def end(self) -> None:
        """Kill and reap the process unless pyct already reaped it. Every way out passes here.

        The status is asked for without waiting first, so a process pyct
        already reaped, whose status was lost on the way out, is never
        killed: its pid may belong to another process by now. A Ctrl-C is
        held until the process is reaped, then goes on.
        """
        if self.status is not None:
            return
        with ctrl_c_held():
            self._kill_and_reap()

    def _kill_and_reap(self) -> None:
        try:
            pid, status = os.waitpid(self.pid, os.WNOHANG)
        except ChildProcessError:
            return
        if pid == 0:
            os.kill(self.pid, signal.SIGKILL)
            _, status = os.waitpid(self.pid, 0)
        self.status = status


def ending(reading: Reading, waited: Waited) -> ExecutionResult:
    """What one input did, from what its process wrote and how it ended."""
    return ExecutionResult(
        lines=reading.lines,
        branches=reading.branches,
        downgrades=reading.downgrades,
        failure=_failure(reading, waited),
    )


def _failure(reading: Reading, waited: Waited) -> Failure | None:
    """How the input ended, by the first rule that holds.

    Facts known to be incomplete are a pyct bug, since a pyct bug must reach
    the exit code. A call that wrote its ending ended that way, as it would
    have in pyct's own process, even when pyct's kill landed as the process
    was exiting. Without one, the process was ended before its call was: by
    pyct at the deadline; before pyct's side of it came up, which is pyct's
    failure; or by a signal or an exit.
    """
    if reading.problem is not None:
        return Failure(kind=FailureKind.PYCT_BUG, detail=reading.problem)
    if reading.ended:
        return reading.end
    if waited.killed:
        return Failure(kind=FailureKind.TIMEOUT, detail="deadline passed")
    if not reading.started:
        detail = f"the input's process ended before its call began: {_how(waited)}"
        return Failure(kind=FailureKind.PYCT_BUG, detail=detail)
    if waited.signal is not None:
        return Failure(kind=FailureKind.CRASHED, detail=_how(waited))
    return Failure(kind=FailureKind.SYSTEM_EXIT, detail=_how(waited))


def _how(waited: Waited) -> str:
    """How the process ended, in the words a line gives."""
    if waited.signal is not None:
        return f"killed by {_named(waited.signal)}"
    return f"exited with code {waited.code}"


def _named(number: int) -> str:
    """A signal as Python's ``signal`` module names it, or by number when it names none."""
    try:
        return signal.Signals(number).name
    except ValueError:
        return f"signal {number}"

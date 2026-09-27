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

``Child`` and ``how`` also serve the process the shell started, which
watches the command's process the same way (see ``launch``).
"""

from __future__ import annotations

import contextlib
import os
import signal
from collections.abc import Callable, Generator
from dataclasses import dataclass
from typing import NoReturn

from pyct.execution.deadline import alarm
from pyct.execution.execute import ExecutionResult
from pyct.results.failure import Failure, FailureKind
from pyct.run.journal import Reading

# the signals whose handler may raise in pyct's process and end what it is doing: a Ctrl-C's
# SIGINT, and SIGTERM, which the command's process stops on (see ``launch``)
STOP_SIGNALS = frozenset({signal.SIGINT, signal.SIGTERM})

# how long past the deadline an input's process may run before pyct kills it: long enough for
# the process's own alarm to end a Python hang, finally blocks included, even on a busy machine
KILL_GRACE = 0.5


class Stopped(BaseException):
    """pyct's process was told to stop, by a SIGTERM (see ``launch``).

    A BaseException, as a Ctrl-C's KeyboardInterrupt is, so pyct's code lets
    it through and ends each process pyct started on the way out. Target
    code that catches BaseException can catch it and go on, so a stop also
    refuses every input after it (see ``refuse_after_a_stop``).
    """


# whether this process was told to stop; once it was, no input starts
_stop_asked = False


def stop() -> NoReturn:
    """Raise ``Stopped``, and refuse every input from now on."""
    global _stop_asked
    _stop_asked = True
    raise Stopped


def stop_asked() -> bool:
    """Whether this process was told to stop, though target code may have caught it."""
    return _stop_asked


def refuse_after_a_stop() -> None:
    """Raise ``Stopped`` again when this process was told to stop, so no input starts."""
    if _stop_asked:
        raise Stopped


class InputStartError(Exception):
    """pyct could not start a process for an input. The message is the system's reason."""


@dataclass(frozen=True)
class Waited:
    """How a process pyct started ended, as the system reported it, and whether pyct ended it.

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

    A Ctrl-C, or another signal in ``STOP_SIGNALS``, is held from before the
    start until pyct holds the pid inside the guard that ends the process on
    the way out, so none lands between the two and leaves the process
    running. It then goes on, as KeyboardInterrupt for a Ctrl-C, once the
    process is ended and reaped.
    """
    child: Child | None = None
    try:
        # a signal held here goes on as the block ends, with the process in the guard's hands
        with _stops_held():
            child = Child(start())
        with alarm(None if until is None else until + KILL_GRACE, child.kill_if_running):
            return child.wait()
    finally:
        if child is not None:
            child.end()


@contextlib.contextmanager
def _stops_held() -> Generator[None]:
    """Hold each signal in ``STOP_SIGNALS`` until the block ends, then let it go on as it would.

    The signal mask holds them for this thread, and a child forked inside the
    block starts with that mask. The system can still hand one to another
    thread of pyct's process, and Python then raises in this thread anyway,
    so a handler that only notes it holds it here too. On the way out the old
    handlers come back, and each noted signal is raised again for them. Like
    the rest of ``run()``, this needs the main thread.
    """
    noted: list[int] = []
    previous = {
        number: signal.signal(number, lambda got, frame: noted.append(got))
        for number in STOP_SIGNALS
    }
    held = signal.pthread_sigmask(signal.SIG_BLOCK, STOP_SIGNALS)
    try:
        yield
    finally:
        # unblocking runs the noting handler for a signal this thread held
        signal.pthread_sigmask(signal.SIG_SETMASK, held)
        for number, handler in previous.items():
            signal.signal(number, signal.SIG_DFL if handler is None else handler)
        for number in dict.fromkeys(noted):
            signal.raise_signal(number)


class Child:
    """One process pyct started, an input's or the command's, from its start until it is reaped."""

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

    def ended(self) -> bool:
        """Whether the process has ended, without waiting. One that has is reaped here.

        Signal 0 sends nothing; it only asks whether the process is there.
        """
        return not self.send_if_running(0)

    def kill_if_running(self, *_: object) -> None:
        """Kill the process unless it has ended. The kill timer's handler: it never raises."""
        if self.send_if_running(signal.SIGKILL):
            self.killed = True

    def send_if_running(self, number: int) -> bool:
        """Send the process signal ``number`` unless it has ended, and say whether it was sent.

        A signal handler can call it, since it never raises. The status is
        asked for without waiting first. A process that ended is reaped here
        and its status kept for ``wait``; one ``wait`` already reaped is left
        alone, so its pid, which may belong to another process by now, gets
        no signal.
        """
        if self.status is not None:
            return False
        try:
            pid, status = os.waitpid(self.pid, os.WNOHANG)
        except ChildProcessError:
            return False
        if pid != 0:
            self.status = status
            return False
        os.kill(self.pid, number)
        return True

    def end(self) -> None:
        """Kill and reap the process unless pyct already reaped it. Every way out passes here.

        The status is asked for without waiting first, so a process pyct
        already reaped, whose status was lost on the way out, is never
        killed: its pid may belong to another process by now. A Ctrl-C, or
        another signal in ``STOP_SIGNALS``, is held until the process is
        reaped, then goes on.
        """
        if self.status is not None:
            return
        with _stops_held():
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
        detail = f"the input's process ended before its call began: {how(waited)}"
        return Failure(kind=FailureKind.PYCT_BUG, detail=detail)
    if waited.signal is not None:
        return Failure(kind=FailureKind.CRASHED, detail=how(waited))
    return Failure(kind=FailureKind.SYSTEM_EXIT, detail=how(waited))


def how(waited: Waited) -> str:
    """How the process ended, in the words an input's line and a failed import's line give."""
    if waited.signal is not None:
        return f"killed by {_named(waited.signal)}"
    return f"exited with code {waited.code}"


def _named(number: int) -> str:
    """A signal as Python's ``signal`` module names it, or by number when it names none."""
    try:
        return signal.Signals(number).name
    except ValueError:
        return f"signal {number}"

"""The command in a process of its own, so the process the shell started outlives the import.

A target's module can end the process that imports it, by ``os._exit`` or
by a signal such as SIGSEGV. pyct imports the target once, in the process
that runs it, so that process cannot be the one that says so. The process
the shell starts forks the command's process before anything else and only
watches it. While the command's process imports the target, a page the two
share names the module. When the command's process ends while the page
names one, the watcher says ``cannot import <module>: <how it ended>``, in
the words an input's line uses, and exits 1. Otherwise the watcher ends as
the command's process ended: with its exit code, or by its signal. A
signal that writes a core is the exception: the watcher says ``pyct's
process was killed by <signal>`` and exits 128 plus the signal's number,
the code a shell gives, so the system records one crash, not two.

The watcher passes on each signal that one process sends another to end
it, so a signal sent to the pid the shell got ends pyct as it always did.
A SIGINT waits ``CTRL_C_GRACE`` first. A Ctrl-C reaches both processes,
since the terminal signals its whole foreground group, and the command's
process ends on it well within that time. So a SIGINT is passed on only
when the command's process still runs after it, as it does when the
SIGINT was sent to the watcher alone. When the command's process ends
by a signal the watcher got too, that ending is the signal's, not the
import's, so the watcher ends the same way.

The command's process ends on a SIGTERM as on a Ctrl-C: it ends its
input's process and cvc5 on the way out, then ends by the SIGTERM. It
ends the same way once the watcher is gone, however the watcher went, so
a SIGKILL sent to the pid the shell got still ends the whole run. Target
code that catches the stop delays that end by ``STOP_GRACE`` at most: a
backstop process ends the command's process then.
"""

from __future__ import annotations

import contextlib
import fcntl
import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable, Generator, Iterable, Sequence
from pathlib import Path
from typing import NoReturn

from pyct.core.branch import PYCT_DIR
from pyct.run.child import flush_streams
from pyct.run.import_watch import ImportWatch
from pyct.run.process import Child, Waited, how
from pyct.run.threads import running

# the signals the watcher passes on to the command's process as soon as it gets them: those
# whose default action ends a process and that one process sends another to end it
_PASSED_ON = frozenset(
    {signal.SIGHUP, signal.SIGQUIT, signal.SIGTERM, signal.SIGUSR1, signal.SIGUSR2}
)
# how long the watcher keeps a SIGINT before it passes it on; a Ctrl-C from the terminal
# reaches the command's process too and ends it well within this
CTRL_C_GRACE = 0.5
# how long the command's process has to end once it is told to stop, before it is ended
# directly; target code that catches BaseException can catch the stop and go on
STOP_GRACE = 1.0
# what a stop's backstop runs: wait, then end its parent by SIGTERM if that is still its parent
_BACKSTOP = (
    "import os, sys, time; parent = int(sys.argv[1]); time.sleep(float(sys.argv[2])); "
    f"os.getppid() == parent and os.kill(parent, {int(signal.SIGTERM)})"
)
# the signals the watcher notes; they are held from before the fork until it does
_NOTED = _PASSED_ON | {signal.SIGINT}

# names the page's and the lifeline's descriptors to a command's process started fresh
_HANDED = "PYCT_WATCHED_BY"
# what a command's process started fresh runs: the pyct this process runs, as ``python -m pyct``.
# pyct's root goes on the import path only until pyct is imported, so the target's path is the
# one a forked command's process gives it
_BOOT = (
    "import runpy, sys; root = sys.argv.pop(1); sys.path.insert(0, root); import pyct; "
    "sys.path.remove(root); runpy.run_module('pyct', run_name='__main__', alter_sys=True)"
)
_PYCT_ROOT = str(Path(PYCT_DIR).parent)
# the signals whose default action writes a core, as POSIX lists them, and SIGEMT where the
# system has it; the watcher does not end by one of these
_WRITES_A_CORE = frozenset(
    getattr(signal, name)
    for name in (
        "SIGABRT",
        "SIGBUS",
        "SIGEMT",
        "SIGFPE",
        "SIGILL",
        "SIGQUIT",
        "SIGSEGV",
        "SIGSYS",
        "SIGTRAP",
        "SIGXCPU",
        "SIGXFSZ",
    )
    if hasattr(signal, name)
)
# how often a watcher that runs other threads looks whether the command's process has ended
_LOOK_EVERY = 0.05

# the command line's work, given the page when a watcher reads it; returns the exit code
type Command = Callable[[ImportWatch | None], int]


class Stopped(BaseException):
    """The command's process got a SIGTERM, or its watcher is gone.

    A BaseException, as a Ctrl-C's KeyboardInterrupt is, so pyct's code lets
    it through and ends each process pyct started on the way out.
    """


def launch(command: Command, argv: Sequence[str]) -> int:
    """Run ``command`` in a process of its own, watched from this one, and end as it ended.

    The command's process returns what ``command`` returns, so it ends
    through the interpreter's own exit, as pyct always has. This process
    returns the exit code it ends with, or ends by the command's signal.
    When no process can start, this one runs the command, unwatched.

    The command's process is forked from this one before pyct does anything
    that could start a thread. A thread already running, such as one a
    host's ``sitecustomize`` started, makes a fork unsafe, so the command's
    process then starts as a fresh interpreter that runs the same command
    line and finds the page and the lifeline through ``_HANDED``.
    """
    handed = os.environ.pop(_HANDED, None)
    if handed is not None:
        return _serve_handed(command, handed)
    threaded = running() > 1
    flush_streams()
    held = signal.pthread_sigmask(signal.SIG_BLOCK, _NOTED)
    try:
        watch = ImportWatch.for_command_line(argv)
        lifeline, kept = os.pipe()
        pid = _spawned(watch, lifeline, argv, held) if threaded else os.fork()
    except OSError:
        return _serve(command, None, held, None)
    # coverage.py cannot see these lines: they run in the child, in a frame begun before the fork
    if pid == 0:  # pragma: no cover
        os.close(kept)
        return _serve(command, watch, held, lifeline)
    os.close(lifeline)
    return _watch(Child(pid), watch, held, kept, threaded)


def _spawned(watch: ImportWatch, lifeline: int, argv: Sequence[str], held: Iterable[int]) -> int:
    """Start the command's process as a fresh interpreter, and return its pid.

    It runs the pyct this process runs, with this interpreter's flags, on
    the same command line. ``-P`` keeps the working directory off the
    import path while pyct boots, as for a fresh input's interpreter. Its
    standard streams are this process's own, and it starts with ``held``
    as its mask.
    """
    for fd in (watch.fd, lifeline):
        os.set_inheritable(fd, True)
    # CPython's own helper, the one multiprocessing starts its workers with; typeshed omits it
    flags = subprocess._args_from_interpreter_flags()  # pyrefly: ignore[missing-attribute]
    fresh = [sys.executable, *flags, "-P", "-c", _BOOT, _PYCT_ROOT, *argv]
    environment = {**os.environ, _HANDED: f"{watch.fd},{lifeline}"}
    return os.posix_spawn(sys.executable, fresh, environment, setsigmask=held)


def _serve_handed(command: Command, handed: str) -> int:
    """Serve as a command's process started fresh, on the descriptors ``handed`` names.

    Its mask came with its start. The descriptors stop being inherited
    here, so the processes it starts in turn do not hold them.
    """
    page, lifeline = (int(fd) for fd in handed.split(","))
    for fd in (page, lifeline):
        os.set_inheritable(fd, False)
    held = signal.pthread_sigmask(signal.SIG_BLOCK, ())
    return _serve(command, ImportWatch(page), held, lifeline)


def _serve(
    command: Command, watch: ImportWatch | None, held: Iterable[int], lifeline: int | None
) -> int:
    """Run ``command`` as the command's process, which stops on a SIGTERM or with its watcher.

    The handlers go in before ``held``, the mask to put back, is put back.
    When the command's process was forked, that mask held SIGTERM from
    before the fork, so none lands before its handler. The watcher may be
    gone before the system could say so, so the pipe is read once here too.
    """
    stops = _Stops(lifeline)
    try:
        with stops.handled():
            signal.pthread_sigmask(signal.SIG_SETMASK, held)
            if stops.alone():
                stops.stop()
            return command(watch)
    except Stopped:
        stops.cancel()
        return _end_by(signal.SIGTERM)


class _Stops:
    """How the command's process stops: on a SIGTERM, and once the watcher is gone.

    Either raises ``Stopped`` wherever the process is, as a Ctrl-C raises
    KeyboardInterrupt, so the input's process and cvc5 are ended on the way
    out, and then the command's process ends by SIGTERM. Target code that
    catches BaseException can catch ``Stopped`` and go on, at its import or
    in a call in this process, so a stop also makes SIGTERM take its default
    action and starts a backstop: a small process of its own that sends
    this one SIGTERM ``STOP_GRACE`` later. This process then ends even while
    that code runs. The backstop is a process, not a thread, so this one
    runs no thread it did not run before, and it keeps SIGALRM, which the
    deadline and the kill timer use, to them. pyct ends the backstop when
    it ends this process itself.

    ``lifeline`` is the read end of a pipe whose write end only the watcher
    holds, and never writes to, so the pipe reads an end of file once the
    watcher is gone, however it went, SIGKILL included. The system says so
    by SIGIO, whose handler reads the pipe itself, so no thread waits on it.
    """

    def __init__(self, lifeline: int | None) -> None:
        self.lifeline = lifeline
        self.backstop: Child | None = None
        self.stopped = False

    @contextlib.contextmanager
    def handled(self) -> Generator[None]:
        """Stop on a SIGTERM, and on a SIGIO that says the watcher is gone, until the block ends."""
        handlers: dict[int, Callable[[int, object], None]] = {signal.SIGTERM: self._on_sigterm}
        if self.lifeline is not None:
            handlers[signal.SIGIO] = self._on_sigio
        previous = {number: signal.signal(number, handler) for number, handler in handlers.items()}
        try:
            if self.lifeline is not None:
                _signal_at_end_of_file(self.lifeline)
            yield
        finally:
            for number, handler in previous.items():
                signal.signal(number, signal.SIG_DFL if handler is None else handler)

    def alone(self) -> bool:
        """Whether the lifeline reads an end of file: the watcher is gone.

        A read that finds nothing yet raises BlockingIOError, and one on a
        descriptor the target closed raises another OSError; neither says the
        watcher is gone.
        """
        if self.lifeline is None:
            return False
        try:
            return os.read(self.lifeline, 1) == b""
        except OSError:
            return False

    def stop(self) -> NoReturn:
        """Raise ``Stopped``, with SIGTERM at its default action and the backstop started once."""
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        if not self.stopped:
            self.stopped = True
            self.backstop = _backstop()
        raise Stopped

    def cancel(self) -> None:
        """End and reap the backstop, once pyct ends this process itself."""
        if self.backstop is not None:
            self.backstop.end()

    def _on_sigterm(self, _number: int, _frame: object) -> None:
        self.stop()

    def _on_sigio(self, _number: int, _frame: object) -> None:
        if self.alone():
            self.stop()


def _backstop() -> Child | None:
    """Start the process that ends this one by SIGTERM ``STOP_GRACE`` from now, or None.

    It is a Python run isolated and without site, so it starts in
    milliseconds, and its standard streams are the null device, so it holds
    none of this process's. It sends the SIGTERM only while this process is
    still its parent: a process that ended some other way has given up its
    pid, which may belong to another process by then. A backstop that cannot
    start leaves the stop to the exception alone.
    """
    argv = [sys.executable, "-I", "-S", "-c", _BACKSTOP, str(os.getpid()), str(STOP_GRACE)]
    null = [(os.POSIX_SPAWN_OPEN, fd, os.devnull, os.O_RDWR, 0) for fd in (0, 1, 2)]
    try:
        return Child(os.posix_spawn(sys.executable, argv, os.environ, file_actions=null))
    except OSError:
        return None


def _signal_at_end_of_file(lifeline: int) -> None:
    """Have the system send this process SIGIO when ``lifeline`` can be read, and not wait on it."""
    fcntl.fcntl(lifeline, fcntl.F_SETOWN, os.getpid())
    flags = fcntl.fcntl(lifeline, fcntl.F_GETFL)
    fcntl.fcntl(lifeline, fcntl.F_SETFL, flags | os.O_ASYNC | os.O_NONBLOCK)


def _watch(child: Child, watch: ImportWatch, held: Iterable[int], kept: int, threaded: bool) -> int:
    """Wait for the command's process to end, then end as it did or say which import ended it.

    ``kept`` is the lifeline's write end, closed once the command's process
    is gone.
    """
    signaled: list[int] = []
    try:
        with _noting(signaled, child, held):
            waited = _waited(child, threaded)
    finally:
        child.end()
        os.close(kept)
    return _ending(waited, watch.module(), signaled)


def _waited(child: Child, threaded: bool) -> Waited:
    """Wait for ``child`` to end.

    With another thread running, the system can hand that thread a signal
    meant for this process, and a main thread blocked in its wait runs the
    handler only once the wait ends. So a threaded watcher looks every
    ``_LOOK_EVERY`` instead, and handles a signal between looks.
    """
    if threaded:
        while not child.ended():
            time.sleep(_LOOK_EVERY)
    return child.wait()


@contextlib.contextmanager
def _noting(signaled: list[int], child: Child, held: Iterable[int]) -> Generator[None]:
    """Note each signal in ``_NOTED`` until the block ends, and pass it on to ``child``.

    A SIGINT goes on ``CTRL_C_GRACE`` after it came, and only when ``child``
    still runs then, since a Ctrl-C from the terminal reached ``child`` too;
    the kill timer's SIGALRM says when. Every other signal goes on at once.
    The handlers go in while the signals are still held from before the
    fork, so none ends this process in between; ``held`` is the mask to put
    back once they are in.
    """

    def note(number: int, _frame: object) -> None:
        signaled.append(number)
        if number == signal.SIGINT:
            signal.setitimer(signal.ITIMER_REAL, CTRL_C_GRACE)
        else:
            child.send_if_running(number)

    def pass_on_ctrl_c(_number: int, _frame: object) -> None:
        child.send_if_running(signal.SIGINT)

    previous = {number: signal.signal(number, note) for number in _NOTED}
    previous[signal.SIGALRM] = signal.signal(signal.SIGALRM, pass_on_ctrl_c)
    signal.pthread_sigmask(signal.SIG_SETMASK, held)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        for number, handler in previous.items():
            signal.signal(number, signal.SIG_DFL if handler is None else handler)


def _ending(waited: Waited, module: str | None, signaled: list[int]) -> int:
    """The watcher's exit code, once the command's process has ended, or its end by a signal.

    An ending while the page names a module is that import's, unless a
    signal the watcher got too ended the command's process. A signal that
    writes a core is said on stderr and given as the exit code a shell gives
    for it, 128 and the signal's number, rather than raised again: that
    would have the system record a second crash, the watcher's own. Any
    other signal ends the watcher too, so a shell sees the same ending.
    """
    if module is not None and waited.signal not in signaled:
        print(f"cannot import {module}: {how(waited)}", file=sys.stderr, flush=True)
        return 1
    if waited.signal is None:
        # Waited.of gives an exit code whenever no signal ended the process
        return waited.code or 0
    if waited.signal in _WRITES_A_CORE:
        print(f"pyct's process was {how(waited)}", file=sys.stderr, flush=True)
        return 128 + waited.signal
    return _end_by(waited.signal)


def _end_by(number: int) -> int:
    """End this process by signal ``number``, by its default action, as the command's process.

    Returns only when the signal does not end this process, with what a
    shell reports for a process a signal ended.
    """
    # SIGKILL and SIGSTOP take no handler, and their default action holds already
    with contextlib.suppress(OSError):
        signal.signal(number, signal.SIG_DFL)
    signal.raise_signal(number)
    return 128 + number

"""The command in a process of its own, so the process the shell started outlives the import.

A target's module can end the process that imports it, by ``os._exit`` or
by a signal such as SIGSEGV. pyct imports the target once, in the process
that runs it, so that process cannot be the one that says so. The process
the shell starts forks the command's process before anything else and only
watches it. While the command's process imports the target, a page the two
share names the module. When the command's process ends while the page
names one, the watcher says ``cannot import <module>: <how it ended>``, in
the words an input's line uses, and exits 1. Otherwise the watcher ends as
the command's process ended: with its exit code, or by its signal.

A Ctrl-C reaches both processes, since the terminal signals its whole
foreground group, so the watcher only notes it and the command's process
ends as it does on any Ctrl-C. A SIGTERM is sent to one process, so the
watcher notes it and passes it on. The command's process ends on a
SIGTERM as on a Ctrl-C: it ends its input's process and cvc5 on the way
out, then ends by the SIGTERM. It ends the same way once the watcher is
gone, however the watcher went, so a SIGKILL sent to the pid the shell
got still ends the whole run. When the command's process ends by a
signal the watcher got too, that ending is the signal's, not the
import's, so the watcher ends the same way.
"""

from __future__ import annotations

import contextlib
import fcntl
import functools
import os
import signal
import sys
from collections.abc import Callable, Generator, Iterable, Sequence

from pyct.run.child import flush_streams
from pyct.run.import_watch import ImportWatch
from pyct.run.process import Child, Waited, how

# the signals the watcher notes; they are held from before the fork until it does
_NOTED = frozenset({signal.SIGINT, signal.SIGTERM})

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
    """
    watch = ImportWatch(argv)
    lifeline, kept = os.pipe()
    flush_streams()
    held = signal.pthread_sigmask(signal.SIG_BLOCK, _NOTED)
    try:
        pid = os.fork()
    except OSError:
        pid = None
    if pid:
        os.close(lifeline)
        return _watch(Child(pid), watch, held, kept)
    os.close(kept)
    if pid is None:
        os.close(lifeline)
        return _serve(command, None, held, None)
    # coverage.py cannot see this line: it runs in the child, in a frame begun before the fork
    return _serve(command, watch, held, lifeline)  # pragma: no cover


def _serve(
    command: Command, watch: ImportWatch | None, held: Iterable[int], lifeline: int | None
) -> int:
    """Run ``command`` as the command's process, which stops on a SIGTERM or with its watcher.

    Either raises ``Stopped`` wherever the process is, as a Ctrl-C raises
    KeyboardInterrupt, so the input's process and cvc5 are ended on the way
    out, and then the command's process ends by SIGTERM. The handlers go in
    while SIGTERM is still held from before the fork; ``held`` is the mask
    to put back. The watcher may be gone before the system could say so, so
    the pipe is read once here too.
    """
    try:
        with _stops_on(lifeline):
            signal.pthread_sigmask(signal.SIG_SETMASK, held)
            if lifeline is not None:
                _stop_if_alone(lifeline)
            return command(watch)
    except Stopped:
        return _end_by(signal.SIGTERM)


@contextlib.contextmanager
def _stops_on(lifeline: int | None) -> Generator[None]:
    """Raise ``Stopped`` on a SIGTERM, and once the watcher is gone, until the block ends.

    ``lifeline`` is the read end of a pipe whose write end only the watcher
    holds, and never writes to, so the pipe reads an end of file once the
    watcher is gone, however it went, SIGKILL included. The system says so
    by SIGIO, whose handler reads the pipe itself, so no thread waits on it.
    """
    handlers: dict[int, Callable[[int, object], None]] = {signal.SIGTERM: _stop}
    if lifeline is not None:
        handlers[signal.SIGIO] = functools.partial(_stop_if_alone, lifeline)
    previous = {number: signal.signal(number, handler) for number, handler in handlers.items()}
    try:
        if lifeline is not None:
            _signal_at_end_of_file(lifeline)
        yield
    finally:
        for number, handler in previous.items():
            signal.signal(number, signal.SIG_DFL if handler is None else handler)


def _signal_at_end_of_file(lifeline: int) -> None:
    """Have the system send this process SIGIO when ``lifeline`` can be read, and not wait on it."""
    fcntl.fcntl(lifeline, fcntl.F_SETOWN, os.getpid())
    flags = fcntl.fcntl(lifeline, fcntl.F_GETFL)
    fcntl.fcntl(lifeline, fcntl.F_SETFL, flags | os.O_ASYNC | os.O_NONBLOCK)


def _stop(_number: int, _frame: object) -> None:
    raise Stopped


def _stop_if_alone(lifeline: int, *_: object) -> None:
    """Raise ``Stopped`` when ``lifeline`` reads an end of file: the watcher is gone.

    A read that finds nothing yet raises BlockingIOError, and one on a
    descriptor the target closed raises another OSError; neither says the
    watcher is gone.
    """
    try:
        gone = os.read(lifeline, 1) == b""
    except OSError:
        return
    if gone:
        raise Stopped


def _watch(child: Child, watch: ImportWatch, held: Iterable[int], kept: int) -> int:
    """Wait for the command's process to end, then end as it did or say which import ended it.

    ``kept`` is the lifeline's write end, closed once the command's process
    is gone.
    """
    signaled: list[int] = []
    try:
        with _noting(signaled, child, held):
            waited = child.wait()
    finally:
        child.end()
        os.close(kept)
    return _ending(waited, watch.module(), signaled)


@contextlib.contextmanager
def _noting(signaled: list[int], child: Child, held: Iterable[int]) -> Generator[None]:
    """Note each SIGINT and SIGTERM until the block ends, and pass a SIGTERM on to ``child``.

    The handlers go in while both signals are still held from before the
    fork, so neither ends this process in between; ``held`` is the mask to
    put back once they are in.
    """

    def note(number: int, _frame: object) -> None:
        signaled.append(number)
        if number == signal.SIGTERM:
            child.send_if_running(number)

    previous = {number: signal.signal(number, note) for number in _NOTED}
    signal.pthread_sigmask(signal.SIG_SETMASK, held)
    try:
        yield
    finally:
        for number, handler in previous.items():
            signal.signal(number, signal.SIG_DFL if handler is None else handler)


def _ending(waited: Waited, module: str | None, signaled: list[int]) -> int:
    """The watcher's exit code, once the command's process has ended, or its end by a signal.

    An ending while the page names a module is that import's, unless a
    signal the watcher got too ended the command's process.
    """
    if module is not None and waited.signal not in signaled:
        print(f"cannot import {module}: {how(waited)}", file=sys.stderr, flush=True)
        return 1
    if waited.signal is not None:
        return _end_by(waited.signal)
    # Waited.of gives an exit code whenever no signal ended the process
    return waited.code or 0


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

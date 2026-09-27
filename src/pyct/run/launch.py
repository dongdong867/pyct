"""The command in a process of its own, so the process the shell started outlives the import.

A target's module can end the process that imports it, by ``os._exit`` or
by a signal such as SIGSEGV. pyct imports the target once, in the process
that runs it, so that process cannot be the one that says so. The process
the shell starts forks the command's process before anything else, or
starts it fresh when a thread already runs (see ``launch``), and only
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
input's process and cvc5 on the way out, then ends by the SIGTERM. Its
guard, a small process it starts first (see ``guard``), sends it that
SIGTERM once the watcher is gone, however the watcher went, so a SIGKILL
sent to the pid the shell got still ends the whole run. When target code
keeps the command's process from acting on a SIGTERM, by one long call in
C or by catching the stop, the guard ends it by SIGKILL about
``STOP_GRACE`` later.
"""

from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable, Generator, Iterable, Sequence
from typing import NoReturn

from pyct.run.child import flush_streams
from pyct.run.guard import guard
from pyct.run.import_watch import ImportWatch
from pyct.run.process import Child, Stopped, Waited, how, stop, stop_asked
from pyct.run.threads import running

# the signals the watcher passes on to the command's process as soon as it gets them: those
# whose default action ends a process and that one process sends another to end it
_PASSED_ON = frozenset(
    {signal.SIGHUP, signal.SIGQUIT, signal.SIGTERM, signal.SIGUSR1, signal.SIGUSR2}
)
# how long the watcher keeps a SIGINT before it passes it on; a Ctrl-C from the terminal
# reaches the command's process too and ends it well within this
CTRL_C_GRACE = 0.5
# the signals the watcher notes; they are held from before the fork until it does
_NOTED = _PASSED_ON | {signal.SIGINT}

# names the page's descriptor, and the lifeline's the guard reads, to a command's process
# started fresh
_HANDED = "PYCT_WATCHED_BY"
# what a command's process started fresh runs: this process's import path, which holds the pyct
# this process runs, and then that pyct, as ``python -m pyct``; so the target's import path is
# the one a forked command's process gives it
_BOOT = (
    "import json, runpy, sys; sys.path[:] = json.loads(sys.argv.pop(1)); "
    "runpy.run_module('pyct', run_name='__main__', alter_sys=True)"
)
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

    It runs the pyct this process runs, with this interpreter's flags and
    import path, on the same command line. ``-P`` keeps the working
    directory off the import path while the boot runs, as for a fresh
    input's interpreter. Its
    standard streams are this process's own, and it starts with ``held``
    as its mask.
    """
    for fd in (watch.fd, lifeline):
        os.set_inheritable(fd, True)
    # CPython's own helper, the one multiprocessing starts its workers with; typeshed omits it
    flags = subprocess._args_from_interpreter_flags()  # pyrefly: ignore[missing-attribute]
    fresh = [sys.executable, *flags, "-P", "-c", _BOOT, json.dumps(sys.path), *argv]
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
    """Run ``command`` as the command's process, which stops on a SIGTERM, guarded when watched.

    The SIGTERM raises ``Stopped`` wherever the process is, as a Ctrl-C
    raises KeyboardInterrupt, so the input's process and cvc5 are ended on
    the way out, and then the process ends by SIGTERM. When the watcher
    gave a lifeline, the guard starts first, on it (see ``guard``); this
    process ends and reaps the guard on every ending of its own.

    The handler goes in before the mask becomes ``held``. A forked command's
    process has SIGTERM blocked from before the fork until then, so none
    lands before its handler. One started fresh starts with ``held``, which
    need not block SIGTERM, so a SIGTERM before its handler takes the
    default action and ends it, as a stop would.
    """
    guarded = None if lifeline is None else guard(lifeline)
    if lifeline is not None:
        os.close(lifeline)
    try:
        code = _stoppable(command, watch, held)
    finally:
        if guarded is not None:
            guarded.end()
    return _end_by(signal.SIGTERM) if code is None else code


def _stoppable(command: Command, watch: ImportWatch | None, held: Iterable[int]) -> int | None:
    """What ``command`` returns, or None when a SIGTERM stopped it.

    A stop that target code caught, which let ``command`` return, stopped it
    all the same.
    """
    previous = signal.signal(signal.SIGTERM, _stop)
    try:
        signal.pthread_sigmask(signal.SIG_SETMASK, held)
        code = command(watch)
    except Stopped:
        return None
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_DFL if previous is None else previous)
    return None if stop_asked() else code


def _stop(_number: int, _frame: object) -> NoReturn:
    """Stop, with SIGTERM at its default action from now on.

    A second SIGTERM then ends the process however the first one's
    unwinding goes, and so does the guard's, if it has to send one.
    """
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    stop()


def _watch(child: Child, watch: ImportWatch, held: Iterable[int], kept: int, threaded: bool) -> int:
    """Wait for the command's process to end, then end as it did or say which import ended it.

    ``kept`` is the lifeline's write end, which the guard reads the other
    end of, closed once the command's process is gone.
    """
    signaled: list[int] = []
    try:
        with _noting(signaled, child, held, kept):
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
def _noting(signaled: list[int], child: Child, held: Iterable[int], kept: int) -> Generator[None]:
    """Note each signal in ``_NOTED`` until the block ends, and pass it on to ``child``.

    A SIGINT goes on ``CTRL_C_GRACE`` after it came, and only when ``child``
    still runs then, since a Ctrl-C from the terminal reached ``child`` too;
    the kill timer's SIGALRM says when. Every other signal goes on at once.
    A SIGTERM is also said to the guard, on ``kept``, the lifeline's write
    end, so the guard ends ``child`` if its handler cannot. The handlers go
    in while the signals are still held from before the fork, so none ends
    this process in between; ``held`` is the mask to put back once they are
    in.
    """

    def note(number: int, _frame: object) -> None:
        signaled.append(number)
        if number == signal.SIGINT:
            signal.setitimer(signal.ITIMER_REAL, CTRL_C_GRACE)
            return
        child.send_if_running(number)
        if number == signal.SIGTERM:
            # a guard that is gone, or never started, has nothing to be told
            with contextlib.suppress(OSError):
                os.write(kept, b"!")

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
    A SIGKILL after the watcher got a SIGTERM is the guard's, ending what
    the SIGTERM could not, so it is the SIGTERM's ending.
    """
    if waited.signal == signal.SIGKILL and signal.SIGTERM in signaled:
        waited = Waited(signal=signal.SIGTERM, code=None)
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

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
watcher notes it and passes it on. An ending the watcher was signaled for
is the signal's, not the import's, so the watcher then ends the same way
as the command's process.
"""

from __future__ import annotations

import contextlib
import mmap
import os
import signal
import struct
import sys
from collections.abc import Callable, Generator, Iterable, Sequence

from pyct.run.child import flush_streams
from pyct.run.process import Child, Waited, how

# the page starts with the length of the module name it holds, zero when it names none
_LENGTH = struct.Struct("<I")
# the signals the watcher notes; they are held from before the fork until it does
_NOTED = frozenset({signal.SIGINT, signal.SIGTERM})

# the command line's work, given the page when a watcher reads it; returns the exit code
type Command = Callable[[ImportWatch | None], int]


class ImportWatch:
    """The page on which the command's process names the module it is importing."""

    def __init__(self, argv: Sequence[str]) -> None:
        """A page every process forked from this one shares, with room for the whole ``argv``.

        A module name is part of one argument, so any name the command line
        gives fits.
        """
        room = len("".join(argv).encode("utf-8", "surrogateescape"))
        self._page = mmap.mmap(-1, _LENGTH.size + room)

    @contextlib.contextmanager
    def importing(self, module_name: str) -> Generator[None]:
        """Name ``module_name`` on the page until the block ends, however it ends."""
        self._write(module_name.encode())
        try:
            yield
        finally:
            self._write(b"")

    def module(self) -> str | None:
        """The module the page names, or None."""
        (length,) = _LENGTH.unpack_from(self._page)
        if length == 0:
            return None
        return self._page[_LENGTH.size : _LENGTH.size + length].decode()

    def _write(self, name: bytes) -> None:
        self._page[_LENGTH.size : _LENGTH.size + len(name)] = name
        _LENGTH.pack_into(self._page, 0, len(name))


def launch(command: Command, argv: Sequence[str]) -> int:
    """Run ``command`` in a process of its own, watched from this one, and end as it ended.

    The command's process returns what ``command`` returns, so it ends
    through the interpreter's own exit, as pyct always has. This process
    returns the exit code it ends with, or ends by the command's signal.
    When no process can start, the command runs in this one, unwatched.
    """
    watch = ImportWatch(argv)
    flush_streams()
    held = signal.pthread_sigmask(signal.SIG_BLOCK, _NOTED)
    try:
        pid = os.fork()
    except OSError:
        pid = None
    if pid:
        return _watch(Child(pid), watch, held)
    signal.pthread_sigmask(signal.SIG_SETMASK, held)
    return command(None if pid is None else watch)


def _watch(child: Child, watch: ImportWatch, held: Iterable[int]) -> int:
    """Wait for the command's process to end, then end as it did or say which import ended it."""
    signaled: list[int] = []
    try:
        with _noting(signaled, child, held):
            waited = child.wait()
    finally:
        child.end()
    return _ending(waited, watch.module(), bool(signaled))


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


def _ending(waited: Waited, module: str | None, signaled: bool) -> int:
    """The watcher's exit code, once the command's process has ended, or its end by a signal."""
    if module is not None and not signaled:
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

"""The input's own process: how it is set up, what it runs, and how it always ends.

pyct runs each input in a process of its own. That process gives the
target an empty stdin and sends what the target writes to stdout to
stderr, so every stdout line stays JSON. A Ctrl-C ends it at once, as a
signal's default action does, so a KeyboardInterrupt raised in it is only
ever the target's own. It writes each fact into the input's journal as the
call makes it, and it ends in ``os._exit`` on every path, so it never
returns into the code that started it, which may be pytest.

The word is "child process", never "fork": a fork is pyct's word for a
branch the target took.
"""

from __future__ import annotations

import contextlib
import os
import signal
import sys
import traceback
from collections.abc import Callable
from typing import NoReturn

from pyct.execution.blame import one_line
from pyct.results.failure import Failure, FailureKind
from pyct.run.journal import JournalWriter

# one call of the target in this process, told to the journal; its failure, or None
type Served = Callable[[JournalWriter], Failure | None]


def serve(writer: JournalWriter, call: Served) -> NoReturn:
    """Settle this process as the input's own, run the call, write how it ended, and exit.

    A raise out of pyct's own code here is a pyct bug on the input's line,
    written as the ending when the journal still takes it.
    """
    try:
        settle(writer)
        writer.end(call(writer))
    except BaseException as error:
        with contextlib.suppress(BaseException):
            writer.end(own_bug(error))
    _flush()
    os._exit(0)


def settle(writer: JournalWriter) -> None:
    """Make this process the input's own: Ctrl-C ends it, stdin is empty, stdout is stderr.

    A process the target forks from this one writes nothing to the journal:
    only the input's own process speaks for the input.
    """
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.pthread_sigmask(signal.SIG_UNBLOCK, {signal.SIGINT})
    _empty_stdin()
    _stdout_to_stderr()
    os.register_at_fork(after_in_child=writer.detach)


def own_bug(error: BaseException) -> Failure:
    """A raise out of pyct's own code in the input's process, as the input's failure."""
    return Failure(
        kind=FailureKind.PYCT_BUG,
        detail=one_line(error),
        traceback="".join(traceback.format_exception(error)),
    )


def _empty_stdin() -> None:
    """The target reads an empty stdin, file descriptor and ``sys.stdin`` alike."""
    empty = os.open(os.devnull, os.O_RDONLY)
    os.dup2(empty, 0)
    os.close(empty)
    sys.stdin = open(0, closefd=False)  # noqa: SIM115 - the process's own stdin, until it exits


def _stdout_to_stderr() -> None:
    """What the target prints or writes to file descriptor 1 lands on stderr."""
    with contextlib.suppress(Exception):
        sys.stdout.flush()
    os.dup2(2, 1)
    sys.stdout = sys.stderr


def _flush() -> None:
    """Hand on what the target wrote before ``os._exit``, which flushes nothing."""
    for stream in (sys.stdout, sys.stderr, sys.__stdout__, sys.__stderr__):
        with contextlib.suppress(Exception):
            stream.flush()  # pyrefly: ignore[missing-attribute]

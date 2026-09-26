"""Stop a call that runs too long, with a SIGALRM timer.

The timer raises inside whatever the target is doing, so a loop, a
helper module, and ``time.sleep`` all stop the same way, and the lines
reached before it stay on the result. Signals only reach the main
thread, and ``setitimer`` is Unix only, so a run is both. The signal can
land between the target returning and the timer being cancelled, so a
call that finished in the last moment can still report a timeout; the
window is sub-millisecond and accepted.

A target that catches ``BaseException`` swallows the one alarm, and a
call inside C never returns to Python for the alarm to raise in. Nothing
here can stop either. In a process of the input's own, pyct's run layer
kills that process shortly after the deadline instead; in pyct's own
process, with ``--in-process``, both run unbounded.
"""

from __future__ import annotations

import signal
import time
import types
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import NoReturn

# a deadline already past still has to fire, and setitimer(0) would cancel instead
_AT_ONCE = 1e-6


class DeadlineError(BaseException):
    """The deadline passed while the target was running.

    A BaseException, not an Exception, so the target's own ``except
    Exception`` cannot swallow it.
    """


# what SIGALRM runs: Python hands it the signal number and the frame it landed in
type Handler = Callable[[int, types.FrameType | None], object]


def deadline(at: float | None) -> AbstractContextManager[None]:
    """Raise DeadlineError at the monotonic instant ``at``. ``None`` sets no timer."""
    return alarm(at, _raise_deadline)


@contextmanager
def alarm(at: float | None, act: Handler) -> Iterator[None]:
    """Run ``act`` from SIGALRM at the monotonic instant ``at``. ``None`` sets no timer.

    The previous handler comes back and the timer is cancelled on the way out.
    """
    if at is None:
        yield
        return
    previous = signal.signal(signal.SIGALRM, act)
    try:
        signal.setitimer(signal.ITIMER_REAL, max(at - time.monotonic(), _AT_ONCE))
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def _raise_deadline(signal_number: int, frame: types.FrameType | None) -> NoReturn:
    # the tests that fire the alarm run without coverage, which a raise here can hang
    raise DeadlineError  # pragma: no cover

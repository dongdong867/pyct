"""Stop a call that runs too long, with a SIGALRM timer.

The timer raises inside whatever the target is doing, so a loop, a
helper module, and ``time.sleep`` all stop the same way, and the lines
reached before it stay on the result. Signals only reach the main
thread, and ``setitimer`` is Unix only, so a run is both. The signal can
land between the target returning and the timer being cancelled, so a
call that finished in the last moment can still report a timeout; the
window is sub-millisecond and accepted. A target that catches
``BaseException`` swallows the one alarm and runs unbounded; a second
alarm would be caught the same way, so nothing here can stop it.
"""

from __future__ import annotations

import signal
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import NoReturn

# a deadline already past still has to fire, and setitimer(0) would cancel instead
_AT_ONCE = 1e-6


class DeadlineError(BaseException):
    """The deadline passed while the target was running.

    A BaseException, not an Exception, so the target's own ``except
    Exception`` cannot swallow it.
    """


@contextmanager
def deadline(at: float | None) -> Iterator[None]:
    """Raise DeadlineError at the monotonic instant ``at``. ``None`` sets no timer."""
    if at is None:
        yield
        return
    previous = signal.signal(signal.SIGALRM, _raise_deadline)
    try:
        signal.setitimer(signal.ITIMER_REAL, max(at - time.monotonic(), _AT_ONCE))
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def _raise_deadline(signal_number: int, frame: object) -> NoReturn:
    raise DeadlineError

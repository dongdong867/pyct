"""A stop that interrupts the cause analysis wherever it is, when the run's stop instant comes.

Checking the clock step by step leaves every step that forgets to check free
to run on, so the bound is a timer instead: SIGALRM at the stop instant
raises ``OutOfTimeError`` in whatever the analysis is doing, and ``explain``
puts the lines it did not reach under ``not worked out``. A timer is armed
only where it can be: with a stop, on the process's main thread, which is
the one signals reach, and with no other real-time timer pending. pyct's
own deadline alarm runs only around a call, never while causes are worked
out, so the two never meet; where a timer cannot be armed, the analysis's
own clock checks still stop it: between lines, and inside each step whose
cost grows with the function or with the inputs.
"""

from __future__ import annotations

import signal
import threading
import types
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import NoReturn

from pyct.results.graphs import OutOfTimeError

# a stop already past still has to fire, and setitimer(0) would cancel instead
_AT_ONCE = 1e-6

# how soon a stop comes again after one a finalizer swallowed: Python prints and drops what a
# `__del__`, a weakref callback or a collected generator's close raises
_AGAIN = 0.05


@contextmanager
def stopping(stop_at: float | None, now: Callable[[], float]) -> Iterator[None]:
    """Raise OutOfTimeError inside the block when ``now()`` reaches ``stop_at``, and again
    every ``_AGAIN`` seconds until the block ends, since a finalizer can swallow one.

    The timer is disarmed and the previous handler restored on the way out,
    however the block ends. It fires only while the block runs: a signal that
    lands on the way out raises nothing.
    """
    if stop_at is None or not _free():
        yield
        return
    armed = [True]
    previous = signal.signal(signal.SIGALRM, _handler(armed))
    try:
        signal.setitimer(signal.ITIMER_REAL, max(stop_at - now(), _AT_ONCE), _AGAIN)
        try:
            yield
        finally:
            armed[0] = False
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def _free() -> bool:
    """Whether a timer can be armed here: on the main thread, with no real-time timer pending."""
    main = threading.current_thread() is threading.main_thread()
    return main and signal.getitimer(signal.ITIMER_REAL)[0] == 0


def _handler(armed: list[bool]) -> Callable[[int, types.FrameType | None], None]:
    """What SIGALRM runs: raise the stop each time while the block runs, and nothing after it."""

    # the tests that fire the timer run without coverage, which a raise from a signal handler
    # can hang (tests/unit/deadline_fires.py)
    def fire(signal_number: int, frame: types.FrameType | None) -> None:  # pragma: no cover
        if armed[0]:
            _stop()

    return fire


def _stop() -> NoReturn:  # pragma: no cover
    raise OutOfTimeError

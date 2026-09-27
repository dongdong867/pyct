"""A stop that interrupts the cause analysis wherever it is, when the run's stop instant comes.

Checking the clock step by step leaves every step that forgets to check free
to run on, so the bound is a signal instead: SIGALRM at the stop instant
raises ``OutOfTimeError`` in whatever the analysis is doing, and ``explain``
puts the lines it did not reach under ``not worked out``.

A watcher thread sends the signal, with ``pthread_kill``, rather than a
kernel timer. A cancelled real-time timer can still post its signal a
moment after ``setitimer`` returns, once the previous handler is back, and
under the default handler that ends the process. A signal the watcher sent
is pending on the main thread before ``pthread_kill`` returns, so once the
watcher is stopped and joined none can come later: the way out takes any
still pending before it puts the previous handler back.

The stop is armed only where it can be: with a stop, on the process's main
thread, which is the one Python runs signal handlers on, and with no
real-time timer pending, whose SIGALRM would reach the stop's handler.
pyct's own deadline alarm runs only around a call, never while causes are
worked out, so the two never meet; where no stop can be armed, the
analysis's own clock checks still stop it: between lines, and inside each
step whose cost grows with the function or with the inputs.
"""

from __future__ import annotations

import signal
import threading
import time
import types
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import NoReturn

from pyct.results.graphs import OutOfTimeError

# how soon a stop comes again after one a finalizer swallowed: Python prints and drops what a
# `__del__`, a weakref callback or a collected generator's close raises
_AGAIN = 0.05

# what SIGALRM ran before the stop, as signal.signal hands it back
type Previous = Callable[[int, types.FrameType | None], object] | int | signal.Handlers | None


@dataclass
class _Stop:
    """One armed stop: whether it may still raise, and what tells its watcher to end."""

    armed: bool = True
    done: threading.Event = field(default_factory=threading.Event)


@dataclass
class _Restore:
    """What the way out puts back: the thread's signal mask, and SIGALRM's handler once the
    stop has replaced it."""

    mask: set[signal.Signals | int]
    previous: list[Previous] = field(default_factory=list)


@contextmanager
def stopping(stop_at: float | None, now: Callable[[], float]) -> Iterator[None]:
    """Raise OutOfTimeError inside the block when ``now()`` reaches ``stop_at``, and again
    every ``_AGAIN`` seconds until the block ends, since a finalizer can swallow one.

    The watcher is stopped and the previous handler restored on the way out,
    however the block ends, and whatever lands on the way: a stop that lands
    there raises nothing, none comes after it, and an interrupt that lands
    there, a Ctrl-C say, reaches the caller once the way out is done.
    """
    if stop_at is None or not _free():
        yield
        return
    stop = _Stop()
    restore = _Restore(set(signal.pthread_sigmask(signal.SIG_BLOCK, set())))
    watcher = threading.Thread(target=_watch, args=(stop, stop_at - now()), daemon=True)
    try:
        restore.previous.append(signal.signal(signal.SIGALRM, _handler(stop)))
        watcher.start()
        yield
    finally:
        # first, and before any call, whose entry may run a handler: from here on a stop
        # raises nothing
        stop.armed = False
        _way_out(stop, watcher, restore)


def _free() -> bool:
    """Whether a stop can be armed here: on the main thread, with no real-time timer pending."""
    main = threading.current_thread() is threading.main_thread()
    return main and signal.getitimer(signal.ITIMER_REAL)[0] == 0


def _watch(stop: _Stop, wait: float) -> None:
    """Send SIGALRM to the main thread after ``wait`` seconds, then every ``_AGAIN``, while armed.

    The way out clears ``armed`` before it ends the watcher, and a send it
    races lands on a handler that raises nothing; once it has joined the
    watcher, no send is under way and none follows.
    """
    main = threading.main_thread().ident
    assert main is not None
    while not stop.done.wait(max(wait, 0)) and stop.armed:
        signal.pthread_kill(main, signal.SIGALRM)
        wait = _AGAIN


def _way_out(stop: _Stop, watcher: threading.Thread, restore: _Restore) -> None:
    """Disarm until it is done, however often something lands in it, then pass on the first
    thing that did: a Ctrl-C there still reaches the caller."""
    landed: list[BaseException] = []
    while True:
        try:
            _disarm(stop, watcher, restore)
        except BaseException as interrupt:  # noqa: BLE001 - passed on once the way out is done
            landed.append(interrupt)
            continue
        break
    if landed:
        raise landed[0]


def _disarm(stop: _Stop, watcher: threading.Thread, restore: _Restore) -> None:
    """Stop the watcher and put SIGALRM's handler and the mask back, with no SIGALRM of the
    stop's after it. Every step can run again: the way out repeats it when something lands."""
    stop.done.set()
    if watcher.ident is not None:
        watcher.join()
    signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGALRM})
    try:
        if signal.SIGALRM in signal.sigpending():
            signal.sigwait({signal.SIGALRM})
        # a signal delivered before the block may wait for Python to run a handler: give it
        # the stop's, which raises nothing now, before the previous one is back
        time.sleep(0)
        if restore.previous:
            signal.signal(signal.SIGALRM, restore.previous[0])
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, restore.mask)


def _handler(stop: _Stop) -> Callable[[int, types.FrameType | None], None]:
    """What SIGALRM runs: raise the stop each time while the block runs, and nothing after it."""

    # the tests that fire the stop run without coverage, which a raise from a signal handler
    # can hang (tests/unit/deadline_fires.py)
    def fire(signal_number: int, frame: types.FrameType | None) -> None:  # pragma: no cover
        if stop.armed:
            _stop()

    return fire


def _stop() -> NoReturn:  # pragma: no cover
    raise OutOfTimeError

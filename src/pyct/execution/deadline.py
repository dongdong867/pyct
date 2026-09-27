"""Stop a call that runs too long, with SIGALRM.

The signal raises inside whatever the target is doing, so a loop, a helper
module, and ``time.sleep`` all stop the same way, and the lines reached
before it stay on the result. Python runs signal handlers on the main
thread only, so a call with a deadline runs there, and ``setitimer`` and
``pthread_kill`` make a run Unix only. The signal can land between the
target returning and the block ending, so a call that finished in the last
moment can still report a timeout; the window is sub-millisecond and
accepted.

No SIGALRM of a deadline raises, or reaches another handler, once its block
has ended. How the signal comes depends on who owns the process:

- The input's own process owns SIGALRM (``own_the_alarm``). pyct's handler
  is installed once and never put back, and the kernel's real-time timer
  sends the signal. The handler raises only while a block runs, so a signal
  the timer posts late, as macOS can after the timer is cancelled, finds it
  and does nothing. No thread runs beside the target.
- Any other process, pyct's own with ``--in-process`` or a program that
  calls ``run()``, keeps its own handler, which a block borrows and puts
  back. A kernel timer's signal cannot be taken back there, so a watcher
  thread sends it to the main thread with ``pthread_kill``, under a lock and
  only while the block runs. The way out stops the sends under that lock
  and takes a signal still on its way before the handler goes back, so none
  comes after it.

A target that catches ``BaseException`` swallows the one alarm, and a call
inside C never returns to Python for the alarm to raise in. Nothing here can
stop either. In a process of the input's own, pyct's run layer kills that
process shortly after the deadline instead; in pyct's own process, with
``--in-process``, both run unbounded.
"""

from __future__ import annotations

import signal
import sys
import threading
import time
import types
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass

# a deadline already past still has to fire, and setitimer(0) would cancel instead
_AT_ONCE = 1e-6

# a SIGALRM handler, as signal.signal takes one and hands it back
type Handler = Callable[[int, types.FrameType | None], object] | int | signal.Handlers


class DeadlineError(BaseException):
    """The deadline passed while the target was running.

    A BaseException, not an Exception, so the target's own ``except
    Exception`` cannot swallow it.
    """


def deadline(at: float | None) -> AbstractContextManager[None]:
    """Raise DeadlineError at the monotonic instant ``at``. ``None`` sets nothing."""
    if at is None:
        return nullcontext()
    if signal.getsignal(signal.SIGALRM) is _owned:
        return _Timed(at)
    return _Sent(at)


def own_the_alarm() -> None:
    """Make SIGALRM the deadline's alone for the rest of this process, the input's own.

    The handler is never put back, so a late signal finds it and does
    nothing. The input's process runs one call, so no late signal can land
    in a later block either.
    """
    signal.signal(signal.SIGALRM, _owned)


@dataclass
class _Running:
    """Whether a block of the owning process's deadline runs: the handler raises only then."""

    now: bool = False


_RUNNING = _Running()


# the tests that fire the alarm run without coverage, which a raise here can hang
def _owned(signal_number: int, frame: types.FrameType | None) -> None:  # pragma: no cover
    """SIGALRM's handler in a process that owns it: raise once, and only inside a block."""
    if _RUNNING.now:
        _RUNNING.now = False
        raise DeadlineError


class _Timed:
    """A deadline the kernel's real-time timer sends, in a process whose SIGALRM is pyct's."""

    def __init__(self, at: float) -> None:
        self.at = at

    def __enter__(self) -> None:
        _RUNNING.now = True
        signal.setitimer(signal.ITIMER_REAL, max(self.at - time.monotonic(), _AT_ONCE))

    def __exit__(self, *_: object) -> None:
        # first, before any call: a signal from here on raises nothing
        _RUNNING.now = False
        signal.setitimer(signal.ITIMER_REAL, 0)


class _Sent:
    """A deadline a watcher thread sends, in a process whose SIGALRM handler pyct borrows.

    ``armed`` holds from the handler's install until the way out begins, and
    the watcher sends only while it holds, under ``lock``. The handler raises
    once, only while it holds, only in the frames the block runs, and never
    over a Ctrl-C on its way out: the block's frame is the one that entered
    it, and a signal that lands as ``__exit__`` begins, before its first
    line, is past the block.
    """

    def __init__(self, at: float) -> None:
        self.at = at
        self.armed = False
        self.sent = False
        self.lock = threading.Lock()
        self.done = threading.Event()
        self.main = threading.get_ident()
        self.home: types.FrameType | None = None
        self.previous: Handler = signal.SIG_DFL
        self.watcher = threading.Thread(target=self._watch, name="pyct deadline", daemon=True)

    def __enter__(self) -> None:
        self.home = sys._getframe(1)
        self.previous = _restorable(signal.getsignal(signal.SIGALRM))
        try:
            signal.signal(signal.SIGALRM, self._fire)
            self.armed = True
            self.watcher.start()
        except BaseException:
            # the alarm that lands here, as the block begins, is the block's: it goes on
            # from the with statement once all of this is undone
            self.__exit__()
            raise

    def __exit__(self, *_: object) -> None:
        # first, before any call: from here on the handler raises nothing
        self.armed = False
        with self.lock:
            # a send under way has ended, and the watcher sends none after this
            pass
        self._put_back()
        self.done.set()
        if self.watcher.ident is not None:
            self.watcher.join()
        self.home = None

    def _watch(self) -> None:
        """Send SIGALRM to the main thread at the instant, unless the block has ended."""
        wait = min(max(self.at - time.monotonic(), 0.0), threading.TIMEOUT_MAX)
        if self.done.wait(wait):
            return
        with self.lock:
            if self.armed:
                self.sent = True
                signal.pthread_kill(self.main, signal.SIGALRM)

    # the tests that fire the alarm run without coverage, which a raise here can hang
    def _fire(self, signal_number: int, frame: types.FrameType | None) -> None:  # pragma: no cover
        """SIGALRM's handler while the block runs: raise once, only inside it."""
        if not self.armed or not self._in_block(frame):
            return
        # a Ctrl-C the alarm lands on goes on; a DeadlineError would take its place
        if isinstance(sys.exception(), KeyboardInterrupt):
            return
        self.armed = False
        raise DeadlineError

    def _in_block(self, frame: types.FrameType | None) -> bool:  # pragma: no cover
        """Whether ``frame`` runs in the block: under the frame that entered it, not its way out."""
        while frame is not None:
            if frame.f_code is _WAY_OUT:
                return False
            if frame is self.home:
                return True
            frame = frame.f_back
        return False

    def _put_back(self) -> None:
        """Put the process's own handler back, taking first a signal the watcher sent.

        A signal sent is pending on this thread, or waits for Python to run
        its handler. The mask holds a pending one while ``sigwait`` takes it.
        ``signal.signal`` runs a waiting one through this deadline's handler,
        which raises nothing now, before it swaps. Another signal's handler,
        a Ctrl-C's, can raise there first, so the swap runs once more, then
        that raise goes on. A raise before the swap leaves this deadline's
        handler, which raises nothing now, rather than let the previous one
        meet a signal still pending; the mask comes back either way.
        """
        held = signal.pthread_sigmask(signal.SIG_BLOCK, set())
        try:
            signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGALRM})
            if self.sent and signal.SIGALRM in signal.sigpending():
                signal.sigwait({signal.SIGALRM})
            try:
                signal.signal(signal.SIGALRM, self.previous)
            except BaseException:
                signal.signal(signal.SIGALRM, self.previous)
                raise
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, held)


_WAY_OUT = _Sent.__exit__.__code__


def _restorable(handler: Handler | None) -> Handler:
    """A handler ``signal.signal`` takes back. One set outside Python reads as None: SIG_DFL."""
    return signal.SIG_DFL if handler is None else handler

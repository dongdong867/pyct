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

- A process pyct owns, the command line's and each input's own, owns
  SIGALRM (``own_the_alarm``, which they call first). pyct's handler is
  installed once and never put back, and the kernel's real-time timer sends
  the signal. The handler raises only while a block runs and once its
  instant has come, so a signal the timer posts late, as macOS can after
  the timer is cancelled, finds it and does nothing. No thread runs beside
  the target, and a C call that checks for signals, such as a regular
  expression's backtracking, stops at the deadline.
- In a process pyct is a guest in, a program that calls ``run()``, pytest
  included, the program keeps its own handler, which a block borrows and
  puts back. A kernel timer's signal cannot be taken back there, so a
  watcher thread sends it to the main thread with ``pthread_kill``, under a
  lock and only while the block runs. The way out stops the sends under
  that lock and takes a signal still on its way before the handler goes
  back, so none comes after it. The watcher needs the GIL to send, so a C
  call that holds it runs to its end first: a backtracking ``re.match`` ran
  2.5 s past a 0.1 s deadline, and a big-int power to its end at 0.665 s,
  where the kernel timer stopped both at about 0.1 s. A Python loop's alarm
  lands about 17 ms late at the median, and the kernel timer's about 7 ms,
  each with its brief hold (``_held_back``), measured on macOS arm64.

A target that catches ``BaseException`` swallows the one alarm, and a call
inside C never returns to Python for the alarm to raise in. Nothing here can
stop either. In a process of the input's own, pyct's run layer kills that
process shortly after the deadline instead; in pyct's own process, with
``--in-process``, both run unbounded, and so does a guest's C call that
holds the GIL.
"""

from __future__ import annotations

import signal
import sys
import threading
import time
import types
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass, field
from typing import NoReturn

from pyct.core.branch import PYCT_DIR
from pyct.execution.stops import STOPS

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
    if _OWNER.owns:
        return _Timed(at)
    return _Sent(at)


def own_the_alarm() -> None:
    """Make SIGALRM the deadline's alone for the rest of this process, one pyct owns.

    pyct owns the command line's process and each input's own. The handler
    is never put back, so a late signal finds it and does nothing. A handler
    target code installs is replaced again as the next call begins.
    """
    _OWNER.owns = True
    signal.signal(signal.SIGALRM, _owned)


@dataclass
class _Hold:
    """How a block's alarm has been held back so far.

    ``since`` is when it was first held for a stop, or None while it has not
    been. ``brief`` is when it was first held briefly, where no stop showed,
    a clock of its own that never starts ``since``. ``owed`` says it was held
    briefly outside pyct's own frames, where it would have raised but for the
    hold, so a block that then ends with no stop still ends by it. ``before`` is the
    exception Python showed as handled when the block began: the caller's,
    or one a frame left set as it ended. From 3.13 a signal handled at a
    loop's backward jump can raise from an offset outside the frame's
    exception table, so an ``except`` body around the loop leaves its
    exception set for the thread. It is not on its way out of the block, so
    no alarm waits for it.
    """

    since: float | None = None
    brief: float | None = None
    owed: bool = False
    before: BaseException | None = None


@dataclass
class _Owner:
    """Whether this process owns SIGALRM, and the block of its deadline that runs now, if any.

    The handler raises only while a block runs, only once its instant has
    come, and only in the frames under ``home``, the frame that entered the
    block, and never over a stop on its way out, for up to ``_HOLD_AT_MOST``;
    one that lands where no stop shows waits a few milliseconds
    (``_held_back``). A signal the timer of an earlier block posts late,
    into a later block, comes before that block's instant, since a timer
    never fires early. A signal that comes after a Ctrl-C cut a block's way
    out short lands outside the block's frames.
    """

    owns: bool = False
    running: bool = False
    at: float = 0.0
    home: types.FrameType | None = None
    hold: _Hold = field(default_factory=_Hold)


_OWNER = _Owner()

# how far before its instant a block's own signal can come: setitimer rounds to a microsecond
_EARLY = 0.001

# how soon an alarm held back comes again
_AGAIN = 0.001

# how long an alarm waits, from when it was first held for a stop, before it raises anyway
_HOLD_AT_MOST = 0.5

# how long an alarm that lands where no stop shows waits, from when it was first held so
_BRIEF_HOLD = 0.003


# the tests that fire the alarm run without coverage, which a raise here can hang
def _owned(signal_number: int, frame: types.FrameType | None) -> None:  # pragma: no cover
    """SIGALRM's handler in a process that owns it: raise once, only inside a block, in time."""
    in_time = _OWNER.running and time.monotonic() >= _OWNER.at - _EARLY
    if not (in_time and _under(frame, _OWNER.home)):
        return
    if _held_back(frame, _OWNER.hold):
        signal.setitimer(signal.ITIMER_REAL, _AGAIN)
        return
    _OWNER.running = False
    _raise_deadline(signal_number, frame)


def _under(frame: types.FrameType | None, home: types.FrameType | None) -> bool:  # pragma: no cover
    """Whether ``frame`` is ``home`` or runs under it."""
    while frame is not None:
        if frame is home:
            return True
        frame = frame.f_back
    return False


def _held_back(frame: types.FrameType | None, hold: _Hold) -> bool:  # pragma: no cover
    """Whether the alarm waits, for a stop on its way out or briefly where no stop shows.

    A DeadlineError would take a stop's place, so the alarm is held back and
    comes again ``_AGAIN`` later, until the stop has left the block or target
    code caught it. A stop is a Ctrl-C's KeyboardInterrupt or a SIGTERM's
    ``Stopped`` (``stops``), other than one already handled as the block
    began (``_Hold.before``). A real stop leaves the block within
    milliseconds, so once the alarm has waited ``_HOLD_AT_MOST`` from when it
    was first held for one, it raises anyway: a handler that never lets its
    stop go would otherwise run with no deadline.

    A stop does not show everywhere it is on its way out. A line tracer's
    callback, pyct's own or a host's ``sys.settrace`` function or
    ``sys.monitoring`` tool, runs in a frame of its own while the stop it
    traces is not yet handled anywhere. And a C call that returns after both
    signals came has Python run SIGALRM's handler before SIGTERM's, so the
    alarm comes before that stop is raised. So an alarm that lands where no
    stop shows, in whatever frame of the block, waits for up to
    ``_BRIEF_HOLD`` from when it was first held so, coming again each
    ``_AGAIN`` or as soon as the watcher can send: long enough for the stop
    to show, and short enough that a hang anywhere in the block, a tracer's
    callback included, still ends near its deadline. One held so outside
    pyct's own frames is owed (``_Hold.owed``).
    """
    now = time.monotonic()
    error = sys.exception()
    if isinstance(error, STOPS) and error is not hold.before:
        if hold.since is None:
            hold.since = now
        return now < hold.since + _HOLD_AT_MOST
    if hold.brief is None:
        hold.brief = now
    held = now < hold.brief + _BRIEF_HOLD
    if held and not (frame is not None and frame.f_code.co_filename.startswith(PYCT_DIR)):
        hold.owed = True
    return held


def _settle(hold: _Hold, error: BaseException | None) -> None:
    """End the block by its alarm when the alarm is owed and nothing else ended the block.

    A block whose alarm was held briefly outside pyct's frames, and that then
    ended with no stop and no raise of the alarm's own, ends by DeadlineError,
    as it would have had the alarm raised where it landed. A raise of the
    target's own gives way to it, as it would have then. A stop does not.
    """
    if hold.owed and not isinstance(error, (DeadlineError, *STOPS)):
        # the way out has run, so this raise, unlike one in a handler, leaves nothing undone
        raise DeadlineError from error


def _raise_deadline(signal_number: int, frame: types.FrameType | None) -> NoReturn:
    """Raise DeadlineError: the one raise both kinds of deadline make."""
    raise DeadlineError  # pragma: no cover


class _Timed:
    """A deadline the kernel's real-time timer sends, in a process whose SIGALRM is pyct's."""

    def __init__(self, at: float) -> None:
        self.at = at

    def __enter__(self) -> None:
        _OWNER.home = sys._getframe(1)
        _OWNER.hold = _Hold(before=sys.exception())
        try:
            if signal.getsignal(signal.SIGALRM) is not _owned:
                signal.signal(signal.SIGALRM, _owned)
            _OWNER.at = self.at
            _OWNER.running = True
            signal.setitimer(signal.ITIMER_REAL, max(self.at - time.monotonic(), _AT_ONCE))
        except BaseException:
            # a Ctrl-C as the timer is armed: the block never began, so nothing of it is left
            self.__exit__()
            raise

    def __exit__(
        self, kind: object = None, error: BaseException | None = None, trace: object = None
    ) -> None:
        # first, before any call: a signal from here on raises nothing
        _OWNER.running = False
        signal.setitimer(signal.ITIMER_REAL, 0)
        _OWNER.home = None
        # the exception handled as the block began, its traceback and its frames go with it
        _OWNER.hold.before = None
        _settle(_OWNER.hold, error)


class _Sent:
    """A deadline a watcher thread sends, in a process whose SIGALRM handler pyct borrows.

    ``armed`` holds from the handler's install until the way out begins, and
    the watcher sends only while it holds, under ``lock``, and while this
    deadline's handler is SIGALRM's. The handler raises once, only for its
    own watcher's signal, only while ``armed`` holds, only in the frames the
    block runs, and never over a stop on its way out, for up to
    ``_HOLD_AT_MOST``, waiting a few milliseconds when it lands where no
    stop shows (``_held_back``): the block's frame is the one that
    entered it. The way in and the way out are not the block: a signal
    that lands as ``__exit__`` begins, before its first line, is past it,
    and one that lands in ``__enter__``, as ``Thread.start`` waits on a
    lock of threading's own, is not yet in it. A raise there can skip the
    lock's taking back, so its ``with`` releases it unlocked. A block whose
    instant has come by the end of ``__enter__`` raises there instead, as
    the block begins; otherwise the watcher sends again ``_AGAIN`` later,
    into the block.

    A Ctrl-C or a SIGTERM is held on this thread while the watcher starts
    and while the way out runs, and goes on once it is done, so it neither
    lands inside the thread's start or its end nor cuts the way out short.
    The watcher starts with them held, so the system hands them to another
    thread only when the caller runs one.
    """

    def __init__(self, at: float) -> None:
        self.at = at
        self.armed = False
        self.sent = False
        self.hold = _Hold()
        self.lock = threading.Lock()
        # held until the way out lets the watcher go; a C lock, so letting go runs no Python
        self.cancel = threading.Lock()
        self.main = threading.get_ident()
        self.home: types.FrameType | None = None
        self.previous: Handler = signal.SIG_DFL
        self.handler = self._fire
        self.watcher: threading.Thread | None = None

    def __enter__(self) -> None:
        self.home = sys._getframe(1)
        self.hold = _Hold(before=sys.exception())
        self.previous = _restorable(signal.getsignal(signal.SIGALRM))
        held = signal.pthread_sigmask(signal.SIG_BLOCK, _STOPS)
        try:
            self.cancel.acquire()
            signal.signal(signal.SIGALRM, self.handler)
            self.armed = True
            self.watcher = threading.Thread(target=self._watch, name="pyct deadline", daemon=True)
            self.watcher.start()
            if time.monotonic() >= self.at:
                # the instant came before the block: it raises here, where no lock is held
                _raise_deadline(signal.SIGALRM, None)  # pragma: no cover
            # inside the try: a stop Python handles as this returns undoes the block too
            signal.pthread_sigmask(signal.SIG_SETMASK, held)
        except BaseException:
            # first, before any call. A raise that lands here, as the block begins, goes on
            # from the with statement once all of this is undone
            self.armed = False
            self._way_out()
            signal.pthread_sigmask(signal.SIG_SETMASK, held)
            raise

    def __exit__(
        self, kind: object = None, error: BaseException | None = None, trace: object = None
    ) -> None:
        # first, before any call: from here on the handler raises nothing
        self.armed = False
        held: set[signal.Signals | int] | None = None
        try:
            held = signal.pthread_sigmask(signal.SIG_BLOCK, _STOPS)
            self._way_out()
        finally:
            if held is not None:
                signal.pthread_sigmask(signal.SIG_SETMASK, held)
        _settle(self.hold, error)

    def _way_out(self) -> None:
        """Stop the sends, put the process's own handler back, and end the watcher."""
        self.armed = False
        try:
            with self.lock:
                # a send under way has ended, and the watcher sends none after this
                pass
            self._let_go()
            self._put_back()
        finally:
            self._let_go()
            if self.watcher is not None and self.watcher.ident is not None:
                self.watcher.join()
            # the thread is freed here, where no Ctrl-C lands in its finalizer
            self.watcher = None
            self.home = None
            # the handler holds this deadline in a cycle, so the exception goes with the block
            self.hold.before = None

    def _let_go(self) -> None:
        """Let the watcher end now rather than at the instant. Letting go twice does nothing."""
        if self.cancel.locked():
            self.cancel.release()

    def _watch(self) -> None:
        """Send SIGALRM to the main thread at the instant, and every ``_AGAIN`` after it,
        until the handler has raised or the block has ended.

        A signal the handler held back for a stop on its way out comes again that way.
        """
        wait = min(max(self.at - time.monotonic(), 0.0), threading.TIMEOUT_MAX)
        while not self.cancel.acquire(timeout=wait):
            with self.lock:
                # the handler check keeps a signal from a handler a way out cut short left behind
                if not (self.armed and signal.getsignal(signal.SIGALRM) is self.handler):
                    return
                self.sent = True
                signal.pthread_kill(self.main, signal.SIGALRM)
            wait = _AGAIN

    # the tests that fire the alarm run without coverage, which a raise here can hang
    def _fire(self, signal_number: int, frame: types.FrameType | None) -> None:  # pragma: no cover
        """SIGALRM's handler while the block runs: raise once, for its own watcher, inside it."""
        if not (self.sent and self.armed and self._in_block(frame)) or _held_back(frame, self.hold):
            return
        self.armed = False
        _raise_deadline(signal_number, frame)

    def _in_block(self, frame: types.FrameType | None) -> bool:  # pragma: no cover
        """Whether ``frame`` runs in the block: under the frame that entered it, not its way
        in or out."""
        edge = frame
        while edge is not None:
            if edge.f_code is _WAY_IN or edge.f_code is _WAY_OUT:
                return False
            edge = edge.f_back
        return _under(frame, self.home)

    def _put_back(self) -> None:
        """Put the process's own handler back, taking first a signal the watcher sent.

        A signal sent is pending on this thread, or waits for Python to run
        its handler. The mask holds a pending one while ``sigwait`` takes it.
        ``signal.signal`` runs a waiting one through this deadline's handler,
        which raises nothing now, before it swaps. Another signal's handler,
        a Ctrl-C's that another thread took, can raise there first, so the
        swap runs once more, then that raise goes on. A raise before the swap
        leaves this deadline's handler, which raises nothing now, rather than
        let the previous one meet a signal still pending; the mask comes back
        either way.
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


_WAY_IN = _Sent.__enter__.__code__
_WAY_OUT = _Sent.__exit__.__code__

# the signals a person stops a run with, held while the watcher starts and while the way out runs
_STOPS = frozenset({signal.SIGINT, signal.SIGTERM})


def _restorable(handler: Handler | None) -> Handler:
    """A handler ``signal.signal`` takes back. One set outside Python reads as None: SIG_DFL."""
    return signal.SIG_DFL if handler is None else handler

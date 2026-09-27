"""The guard: a small process that ends pyct's process when pyct's own handler cannot.

pyct's process stops on a SIGTERM by raising ``Stopped`` from a Python
handler, so it ends its input's process and cvc5 on the way out. Python
runs a handler only between bytecodes, so the handler waits while target
code runs one long call in C, and target code that catches BaseException
can catch the stop and go on. The guard depends on neither.

The watcher starts the guard as its own child, right after pyct's process,
with the lifeline as the guard's stdin: a pipe whose write end only the
watcher holds. The guard is never a child of pyct's process, where target
code runs and could wait for it or reap it. It blocks on one read. A byte
means the watcher passed a SIGTERM on to pyct's process. An end of file
means the watcher is gone, however it went, SIGKILL included, and the
guard sends pyct's process that SIGTERM itself. Either way the guard then
gives pyct's process ``STOP_GRACE`` to end by its handler, and ends it by
SIGKILL if it still runs, whatever it is doing. So the end comes about
``STOP_GRACE`` after the stop, give or take ``LOOK_EVERY``. A guard that
cannot start leaves the stop to the handler alone, and leaves nothing
watching for the watcher's loss.

The guard signals pyct's process only while that pid names a process. The
watcher reaps pyct's process, so that pid stays pyct's while the watcher
lives; once the watcher is gone, pyct's process is reaped as it ends, and
the guard stops looking within ``LOOK_EVERY``. The system hands pids out in
turn, so one is reused only after the others have been, far longer than
that. The watcher ends and reaps its guard on every ending of its own; a
guard whose watcher is gone ends once pyct's process has. It runs in a
process group of its own, so a Ctrl-C from the terminal does not end it
before it acts. It is a Python run isolated and without site, which
starts in milliseconds and no thread, and its standard output and error
are the null device, so it holds none of pyct's.
"""

from __future__ import annotations

import os
import sys

from pyct.run.process import Child

# how long pyct's process has to end by its own handler once it is told to stop; target code
# that catches BaseException, or runs one long call in C, makes the guard end it then
STOP_GRACE = 1.0
# how often the guard looks whether pyct's process still runs while it waits out the grace
LOOK_EVERY = 0.05

# what the guard runs; its arguments are pyct's process's pid, STOP_GRACE and LOOK_EVERY
_GUARD = """
import os, signal, sys, time
target, grace, every = int(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3])


def send(number):
    try:
        os.kill(target, number)
    except OSError:
        return False
    return True


asked = os.read(0, 1)
if not asked:
    send(signal.SIGTERM)
deadline = time.monotonic() + grace
while send(0) and time.monotonic() < deadline:
    time.sleep(every)
send(signal.SIGKILL)
"""


def guard(lifeline: int, target: int) -> Child | None:
    """Start the guard of pyct's process ``target``, reading ``lifeline``, or None.

    A guard that cannot start leaves a stop to pyct's own handler.
    """
    argv = [
        sys.executable,
        *("-I", "-S", "-c", _GUARD),
        *(str(target), str(STOP_GRACE), str(LOOK_EVERY)),
    ]
    streams = [
        (os.POSIX_SPAWN_DUP2, lifeline, 0),
        (os.POSIX_SPAWN_OPEN, 1, os.devnull, os.O_WRONLY, 0),
        (os.POSIX_SPAWN_OPEN, 2, os.devnull, os.O_WRONLY, 0),
    ]
    try:
        pid = os.posix_spawn(
            sys.executable, argv, os.environ, file_actions=streams, setpgroup=0, setsigmask=()
        )
    except OSError:
        return None
    return Child(pid)

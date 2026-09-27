"""The guard: a small process that ends pyct's process when pyct's own handler cannot.

pyct's process stops on a SIGTERM by raising ``Stopped`` from a Python
handler, so it ends its input's process and cvc5 on the way out. Python
runs a handler only between bytecodes, so the handler waits while target
code runs one long call in C, and target code that catches BaseException
can catch the stop and go on. The guard depends on neither.

pyct's process starts its guard first, with the lifeline as the guard's
stdin: a pipe whose write end only the watcher holds. The guard blocks on
one read of it. A byte means the watcher passed a SIGTERM on to pyct's
process. An end of file means the watcher is gone, however it went,
SIGKILL included, and the guard sends pyct's process that SIGTERM itself.
Either way the guard then gives pyct's process ``STOP_GRACE`` to end by its
handler, and ends it by SIGKILL if it still runs, whatever it is doing. So
the end comes about ``STOP_GRACE`` after the stop, give or take
``LOOK_EVERY``. A guard that cannot start leaves the stop to the handler
alone.

The guard acts only while pyct's process is still its parent: a process
that ended has given up its pid, which may belong to another process by
then. pyct's process ends and reaps its guard on every ending of its own.
When it ends some other way, by a crash, the guard ends as its read
returns, once the watcher's end of the lifeline closes, or within
``LOOK_EVERY`` if it is already waiting out the grace. It runs in a
process group of its own, so a Ctrl-C from the terminal does not end it
before it acts. It is a Python run isolated and without
site, which starts in milliseconds and no thread, and its standard output
and error are the null device, so it holds none of pyct's.
"""

from __future__ import annotations

import os
import sys

from pyct.run.process import Child

# how long pyct's process has to end by its own handler once it is told to stop; target code
# that catches BaseException, or runs one long call in C, makes the guard end it then
STOP_GRACE = 1.0
# how often the guard looks whether pyct's process is still its parent while it waits
LOOK_EVERY = 0.05

# what the guard runs; its arguments are pyct's process's pid, STOP_GRACE and LOOK_EVERY
_GUARD = """
import os, signal, sys, time
parent, grace, every = int(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3])
asked = os.read(0, 1)
if os.getppid() == parent and not asked:
    os.kill(parent, signal.SIGTERM)
deadline = time.monotonic() + grace
while os.getppid() == parent and time.monotonic() < deadline:
    time.sleep(every)
if os.getppid() == parent:
    os.kill(parent, signal.SIGKILL)
"""


def guard(lifeline: int, parent: int | None = None) -> Child | None:
    """Start the guard of ``parent``, this process when not given, on ``lifeline``, or None.

    A guard that cannot start leaves a stop to pyct's own handler.
    """
    argv = [
        sys.executable,
        *("-I", "-S", "-c", _GUARD),
        *(str(os.getpid() if parent is None else parent), str(STOP_GRACE), str(LOOK_EVERY)),
    ]
    streams = [
        (os.POSIX_SPAWN_DUP2, lifeline, 0),
        (os.POSIX_SPAWN_OPEN, 1, os.devnull, os.O_WRONLY, 0),
        (os.POSIX_SPAWN_OPEN, 2, os.devnull, os.O_WRONLY, 0),
    ]
    try:
        pid = os.posix_spawn(sys.executable, argv, os.environ, file_actions=streams, setpgroup=0)
    except OSError:
        return None
    return Child(pid)

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

pyct's process ends its input's process on its own way out, which a
SIGKILL skips. So the guard also holds the watcher's page open, on which
pyct's process names the input's process it runs (see ``watch_page``).
Sweep ends the command it runs, the lister or an entry's ``pyct run``, on
its own way out too, and that command leads a session of its own, so
sweep names that command's process group on the page. In place of
the bare SIGKILL, the guard sends pyct's process SIGSTOP, which keeps it
from starting or reaping anything once the stop lands. It then sends
SIGKILL to the pid the page names while that pid is still a child of the
pyct process it has just sent SIGSTOP, as the system tells its parent, to
the group the page names while its leader is still such a child, and
then to pyct's process. A pid that is pyct's child is one pyct has not
reaped, so it is still the input's own. A session's leader cannot leave
its group, and a group's id is not handed out again while its leader is
unreaped, so that group is still the command's own. So the input's
process and the command's group get their SIGKILL before the watcher can
reap pyct's process and end the guard. When the SIGSTOP finds pyct's
process gone, the guard signals nothing more.

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
from pyct.run.watch_page import GROUP_AT, INPUT_AT

# how long pyct's process has to end by its own handler once it is told to stop; target code
# that catches BaseException, or runs one long call in C, makes the guard end it then
STOP_GRACE = 1.0
# how often the guard looks whether pyct's process still runs while it waits out the grace
LOOK_EVERY = 0.05

# what the guard runs; its arguments are pyct's process's pid, the page's descriptor, where the
# page holds the input's pid and the group's id, each a C int in the machine's byte order, as
# watch_page writes them, then STOP_GRACE and LOOK_EVERY. A process's parent comes from /proc on
# Linux and from ps elsewhere
_GUARD = """
import os, signal, sys, time
target, page = int(sys.argv[1]), int(sys.argv[2])
input_at, group_at = int(sys.argv[3]), int(sys.argv[4])
grace, every = float(sys.argv[5]), float(sys.argv[6])


def send(pid, number):
    try:
        os.kill(pid, number)
    except OSError:
        return False
    return True


def named(at):
    try:
        return int.from_bytes(os.pread(page, 4, at), sys.byteorder, signed=True)
    except OSError:
        return 0


def parent(pid):
    try:
        if sys.platform == "linux":
            with open(f"/proc/{pid}/stat") as stat:
                return int(stat.read().rpartition(")")[2].split()[1])
        import subprocess

        told = subprocess.run(["/bin/ps", "-o", "ppid=", "-p", str(pid)], capture_output=True)
        return int(told.stdout)
    except (OSError, ValueError, IndexError):
        return 0


def end():
    if not send(target, signal.SIGSTOP):
        return
    pid, group = named(input_at), named(group_at)
    if pid > 0 and parent(pid) == target:
        send(pid, signal.SIGKILL)
    if group > 0 and parent(group) == target:
        # a negative pid names the group with that id, as killpg does
        send(-group, signal.SIGKILL)
    send(target, signal.SIGKILL)


asked = os.read(0, 1)
if not asked:
    send(target, signal.SIGTERM)
deadline = time.monotonic() + grace
while send(target, 0):
    if time.monotonic() >= deadline:
        end()
        break
    time.sleep(every)
"""


def guard(lifeline: int, target: int, page: int) -> Child | None:
    """Start the guard of pyct's process ``target``, reading ``lifeline`` and ``page``, or None.

    ``page`` is the descriptor of the watcher's page. It is open in the guard
    under the same number, and is not inherited again once the guard has
    started. A guard that cannot start leaves a stop to pyct's own handler.
    """
    argv = [
        sys.executable,
        *("-I", "-S", "-c", _GUARD),
        *(str(target), str(page), str(INPUT_AT), str(GROUP_AT), str(STOP_GRACE), str(LOOK_EVERY)),
    ]
    streams = [
        (os.POSIX_SPAWN_DUP2, lifeline, 0),
        (os.POSIX_SPAWN_OPEN, 1, os.devnull, os.O_WRONLY, 0),
        (os.POSIX_SPAWN_OPEN, 2, os.devnull, os.O_WRONLY, 0),
    ]
    # the page keeps its own number in the guard, since it may hold any number, and on macOS a
    # file action that copies a descriptor onto the number it holds leaves it closed on exec
    os.set_inheritable(page, True)
    try:
        pid = os.posix_spawn(
            sys.executable, argv, os.environ, file_actions=streams, setpgroup=0, setsigmask=()
        )
    except OSError:
        return None
    finally:
        os.set_inheritable(page, False)
    return Child(pid)

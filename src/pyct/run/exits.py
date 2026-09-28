"""The system's notice that a process pyct started has ended, waited for up to an instant.

kqueue tells of it where the system has kqueue, macOS and the BSDs, and a
pidfd elsewhere, Linux 5.3 or later. A system that has neither, or refuses
the call, as an older kernel or a container's syscall filter does, gives no
notice, and the caller asks the process itself instead. Nothing here reaps
the process, so its pid stays its own until the caller reaps it.
"""

from __future__ import annotations

import errno
import math
import os
import select
import time

# the longest single wait: poll takes milliseconds as a C int, so a budget of weeks waits in steps
LONGEST_WAIT = 86_400.0

# what a system without pidfds, or one that forbids them, says when asked for one
_NO_PIDFD = frozenset({errno.ENOSYS, errno.EPERM})


def ends_by(pid: int, instant: float) -> bool | None:
    """Whether the process ``pid``, one of pyct's not yet reaped, ends by the monotonic ``instant``.

    None when the system gives no notice.
    """
    while True:
        left = max(instant - time.monotonic(), 0.0)
        step = min(left, LONGEST_WAIT)
        noticed = _kqueue_says(pid, step) if hasattr(select, "kqueue") else _pidfd_says(pid, step)
        if noticed is not False or step == left:
            return noticed


def _kqueue_says(pid: int, left: float) -> bool:
    """Whether kqueue tells of the process's exit within ``left`` seconds."""
    queue = select.kqueue()
    try:
        exit_note = select.kevent(
            pid,
            filter=select.KQ_FILTER_PROC,
            flags=select.KQ_EV_ADD | select.KQ_EV_ONESHOT,
            fflags=select.KQ_NOTE_EXIT,
        )
        events = queue.control([exit_note], 1, left)
    finally:
        queue.close()
    for event in events:
        # a process that already ended cannot be watched, and says so as ESRCH
        if event.flags & select.KQ_EV_ERROR and event.data != errno.ESRCH:
            raise OSError(event.data, os.strerror(event.data))
    return bool(events)


def _pidfd_says(pid: int, left: float) -> bool | None:
    """Whether the process's pidfd reads as ready, as it does once the process ended, in time.

    None when the system has no pidfd or refuses one.
    """
    try:
        notice = os.pidfd_open(pid)  # pyrefly: ignore[missing-attribute]
    except AttributeError:
        return None
    except OSError as error:
        if error.errno in _NO_PIDFD:
            return None
        raise
    try:
        poller = select.poll()
        poller.register(notice, select.POLLIN)
        return bool(poller.poll(math.ceil(left * 1000)))
    finally:
        os.close(notice)

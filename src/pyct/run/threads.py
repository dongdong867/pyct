"""How many threads pyct's process runs, as the system counts them.

A thread a C library started counts as much as one Python started, since a
copy of the process can hang on a lock either one held. Python's
``threading`` module sees only its own, so the count comes from the system
where it gives one: the task's thread count on macOS, the task directory on
Linux.

ctypes, which reads the task's count, is imported as this module imports,
before a target's folder joins the import path, and leaves ``sys.modules``
again with what it imported, ``sysconfig`` on Python 3.13 and later, so a
target imports its own copies from its path, as plain Python would.
"""

from __future__ import annotations

import contextlib
import functools
import importlib
import os
import struct
import sys
import threading
from collections.abc import Callable
from types import ModuleType

from pyct.run.as_found import modules_as_found

# proc_pidinfo's PROC_PIDTASKINFO flavor: a proc_taskinfo, 96 bytes, pti_threadnum at byte 84
_TASK_INFO = 4
_TASK_INFO_SIZE = 96
_THREAD_COUNT_AT = 84


def _ctypes() -> ModuleType:
    """ctypes, imported with ``sys.modules`` left as it was found."""
    with modules_as_found():
        return importlib.import_module("ctypes")


_CTYPES = _ctypes()


def running() -> int:
    """The threads this process runs, the main one included."""
    counted = None
    if sys.platform == "darwin":
        counted = _darwin()
    elif sys.platform.startswith("linux"):
        with contextlib.suppress(OSError):
            counted = len(os.listdir("/proc/self/task"))
    return threading.active_count() if counted is None else counted


def _darwin() -> int | None:
    """The task's own thread count, or None when the system does not give it."""
    info = _CTYPES.create_string_buffer(_TASK_INFO_SIZE)
    written = _proc_pidinfo()(os.getpid(), _TASK_INFO, 0, info, _TASK_INFO_SIZE)
    if written != _TASK_INFO_SIZE:
        return None
    return struct.unpack_from("<i", info.raw, _THREAD_COUNT_AT)[0]


@functools.cache
def _proc_pidinfo() -> Callable[..., int]:
    """libproc's proc_pidinfo, looked up once: pyct asks before every input."""
    return _CTYPES.CDLL(None).proc_pidinfo

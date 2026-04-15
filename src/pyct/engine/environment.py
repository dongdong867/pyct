"""Environment patches required for Concolic tracking to work end-to-end.

Python has several built-in protocols that short-circuit through C-level
slots, stripping any Python-level subclass information from return values.
The main offender is ``len()``: it calls ``__len__``, immediately coerces
the result to ``Py_ssize_t`` via ``_PyNumber_Index``, and wraps the raw
integer in a fresh ``PyLong``. A ``ConcolicInt`` returned from
``ConcolicStr.__len__`` is discarded and the symbolic ``str.len``
expression is lost.

The fix, borrowed from upstream (libct/explore.py:46) and our legacy
benchmark runner (pyct-legacy/src/pyct/environment_preparer.py:61), is a
one-line monkey-patch: ``builtins.len = lambda x: x.__len__()``. This
bypasses the C coercion entirely and returns whatever ``__len__`` returns
— a ConcolicInt with the symbolic expression preserved.

Two supporting patches are ported alongside:

* ``socket.getaddrinfo`` wraps its args in ``unwrap_concolic`` so DNS
  lookups on concolic strings don't crash the C socket module.
* ``sys.setrecursionlimit`` is raised so deeply recursive targets don't
  trip RecursionError before the engine can explore them.

All patches are installed inside a context manager and restored on exit,
so running ``Engine.explore`` does not permanently mutate global state.
"""

from __future__ import annotations

import builtins
import socket
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from pyct.utils.concolic_converter import unwrap_concolic

_RECURSION_LIMIT = 1_000_000


@contextmanager
def prepared_environment() -> Iterator[None]:
    """Install the Concolic runtime patches for the duration of the block.

    Saves and restores the originals so multiple exploration runs don't
    accumulate state and so non-PyCT code running after an exploration
    sees the pre-patch environment.
    """
    original_len = builtins.len
    original_getaddrinfo = socket.getaddrinfo
    original_recursion_limit = sys.getrecursionlimit()

    builtins.len = _concolic_len  # pyrefly: ignore[bad-assignment]
    socket.getaddrinfo = _make_socket_getaddrinfo_wrapper(original_getaddrinfo)  # pyrefly: ignore[bad-assignment]
    sys.setrecursionlimit(max(original_recursion_limit, _RECURSION_LIMIT))

    try:
        yield
    finally:
        builtins.len = original_len  # pyrefly: ignore[bad-assignment]
        socket.getaddrinfo = original_getaddrinfo  # pyrefly: ignore[bad-assignment]
        sys.setrecursionlimit(original_recursion_limit)


def _concolic_len(obj: Any) -> Any:
    """Bypass ``PyObject_Size`` so ConcolicStr.__len__ returns a ConcolicInt."""
    return obj.__len__()


def _make_socket_getaddrinfo_wrapper(original: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap socket.getaddrinfo so concolic args get unwrapped before the C call."""

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return original(
            *(unwrap_concolic(a) for a in args),
            **{k: unwrap_concolic(v) for k, v in kwargs.items()},
        )

    return wrapper

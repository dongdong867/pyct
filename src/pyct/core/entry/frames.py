"""Rebinding names in a running frame, as a piece's hook does in the target's own frame."""

from __future__ import annotations

import ctypes
import sys
import types
from collections.abc import Mapping

# Python 3.12 hands out a frame's locals as a dict apart from the frame, which CPython's
# PyFrame_LocalsToFast writes back; from 3.13 the frame's `f_locals` writes through
if sys.version_info < (3, 13):
    _LOCALS_TO_FAST = ctypes.pythonapi.PyFrame_LocalsToFast
    _LOCALS_TO_FAST.argtypes = (ctypes.py_object, ctypes.c_int)
    _LOCALS_TO_FAST.restype = None


def rebind(frame: types.FrameType, values: Mapping[str, object]) -> None:
    """Bind each name in ``values`` that ``frame`` has bound now to the value given.

    A name the frame has not bound stays unbound, and a name not given keeps
    its value. It writes a function's locals and parameters, its cell and
    free variables, a generator's frame between its yields, and a module's
    own names. A cell or free variable is one cell, so each function that
    shares it sees the new value. On Python 3.12 a dict the function took
    from ``locals()`` earlier shows the new values too.
    """
    held = frame.f_locals
    for name, value in values.items():
        if name in held:
            held[name] = value
    if sys.version_info < (3, 13):
        _LOCALS_TO_FAST(frame, 0)

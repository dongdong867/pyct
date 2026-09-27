"""Wrapping: `len`, `ord` and `chr` bound to pyct's own in each module of the target's package.

A module finds a name it neither defines nor imports in its builtins, the
mapping its ``__builtins__`` holds, which Python sets to the ``builtins``
module's own dict when the module runs without one. The loader hands each
module of the package a copy of that dict instead, with the three names
bound to the functions `pyct.core.substitutes.BOUND` names, so every call
that finds the name in the module reaches pyct's: a direct call, one in a
method or a nested function, and a function the module hands on, as in
``map(len, items)``. A module that defines or imports its own `len` finds
that first. The module's code, its globals, its ``dir()`` and ``builtins``
itself stay as they are.

The copy holds the builtins as they are when the module runs: a name added
to ``builtins``, or one replaced there, later on reaches the modules loaded
after it. An exact dict keeps Python's fast lookup of every global and
builtin name in the module.
"""

from __future__ import annotations

import builtins

from pyct.core.substitutes import BOUND


def bound_builtins() -> dict[str, object]:
    """The builtins a module of the target's package runs with.

    Python's own as they are now, but for each name `BOUND` names, which is
    pyct's while ``builtins`` still holds Python's own under it: a name
    something else replaced for the whole process keeps its replacement.
    """
    namespace = dict(vars(builtins))
    for name, (python, pyct) in BOUND.items():
        if namespace.get(name) is python:
            namespace[name] = pyct
    return namespace

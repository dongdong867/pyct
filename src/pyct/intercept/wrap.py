"""Wrapping: `len`, `ord` and `chr` bound to pyct's own in each module of the target's package.

A module finds a name it neither defines nor imports in its builtins, the
mapping its ``__builtins__`` holds, which Python sets to the ``builtins``
module's own dict when the module runs without one. The loader hands each
module of the package a `LiveBuiltins` instead, which answers every name
with what ``builtins`` holds when the name is looked up, but for the three
names `pyct.core.substitutes.BOUND` names: while ``builtins`` holds
Python's own under one of them, the module finds pyct's. So every call that
finds the name in the module reaches pyct's, a direct call, one in a method
or a nested function, and a function the module hands on, as in
``map(len, items)``, and a name added to or replaced in ``builtins`` later,
such as the `_` that ``gettext.install`` adds, is found as plain Python
finds it. A module that defines or imports its own `len` finds that first.
The module's code, its globals, its ``dir()`` and ``builtins`` itself stay
as they are.

Python looks a name up in a builtins mapping that is not exactly a dict
through its ``__getitem__``, one Python call per builtin name the module
reads. The mapping also holds a copy of every builtin, for the few lookups
CPython makes straight into the dict, such as ``__import__`` for an
``import`` statement; that copy is as ``builtins`` was when the module ran.
"""

from __future__ import annotations

import builtins

from pyct.core.substitutes import BOUND

_BUILTINS = vars(builtins)


class LiveBuiltins(dict[str, object]):
    """A module's builtins: what ``builtins`` holds now, with pyct's `len`, `ord` and `chr`.

    A write through the module's ``__builtins__`` reaches ``builtins``, as it
    does in plain Python, where that mapping is ``builtins``' own dict.
    """

    __slots__ = ()

    def __init__(self) -> None:
        super().__init__(_BUILTINS)

    def __getitem__(self, name: str) -> object:
        value = _BUILTINS[name]
        bound = BOUND.get(name)
        return bound[1] if bound is not None and value is bound[0] else value

    def get(self, name: str, default: object = None) -> object:  # pyrefly: ignore[bad-override]
        return self[name] if name in _BUILTINS else default

    def __contains__(self, name: object) -> bool:
        return name in _BUILTINS

    def __setitem__(self, name: str, value: object) -> None:
        _BUILTINS[name] = value
        super().__setitem__(name, value)

    def __delitem__(self, name: str) -> None:
        del _BUILTINS[name]
        super().pop(name, None)


def bound_builtins() -> LiveBuiltins:
    """The builtins a module of the target's package runs with (see `LiveBuiltins`)."""
    return LiveBuiltins()

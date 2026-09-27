"""Wrapping: `len`, `ord` and `chr` bound to pyct's own in each module of the target's package.

A module finds a name it neither defines nor imports in its builtins, the
mapping its ``__builtins__`` holds, which Python sets to the ``builtins``
module's own dict when the module runs without one. The loader hands each
module of the package a `LiveBuiltins` instead, which answers every name
with what ``builtins`` holds when the name is looked up, but for the three
names `pyct.core.bound.BOUND` names: while ``builtins`` holds
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
reads: its global names, an ``import`` statement's ``__import__`` and a
``class`` statement's ``__build_class__`` on CPython 3.12. Every method a
dict has reads and writes ``builtins`` as it is now, as the module's
``__builtins__`` does in plain Python, where it is ``builtins``' own dict. A
copy of ``builtins`` it holds as well, kept in step with every write made
through it, serves only C code that reads a dict's storage without its
methods; a name added to ``builtins`` otherwise is missing from that copy.
"""

from __future__ import annotations

import builtins
import copy
from collections.abc import ItemsView, Iterable, Iterator, KeysView, ValuesView

from pyct.core.bound import BOUND

_BUILTINS = vars(builtins)
# dict's own, held here: a write may clear ``builtins``, and these must still run after it
_CLEAR, _UPDATE = dict.clear, dict.update


class LiveBuiltins(dict[str, object]):
    """A module's builtins: what ``builtins`` holds now, with pyct's `len`, `ord` and `chr`.

    Every read answers from ``builtins``, and every write, removal or clear
    acts on it. A copy, by ``copy``, `copy.copy` or pickle, is a plain dict of
    what a lookup finds now, as a copy of ``builtins``' own dict is a plain
    dict.
    """

    __slots__ = ()

    def __init__(self) -> None:
        super().__init__(_BUILTINS)

    def _synced(self) -> None:
        """Keep the copy in step with ``builtins`` after a write through this mapping."""
        _CLEAR(self)
        _UPDATE(self, _BUILTINS)

    def _now(self) -> dict[str, object]:
        """What a lookup of each name finds now, as a plain dict in ``builtins``' order."""
        return {name: self[name] for name in _BUILTINS}

    def __getitem__(self, name: str) -> object:
        value = _BUILTINS[name]
        bound = BOUND.get(name)
        return bound[1] if bound is not None and value is bound[0] else value

    def get(self, name: str, default: object = None) -> object:  # pyrefly: ignore[bad-override]
        return self[name] if name in _BUILTINS else default

    def __contains__(self, name: object) -> bool:
        return name in _BUILTINS

    def __iter__(self) -> Iterator[str]:
        return iter(_BUILTINS)

    def __reversed__(self) -> Iterator[str]:
        return reversed(_BUILTINS)

    def __len__(self) -> int:
        return len(_BUILTINS)

    # views that read through the methods above, so they stay live as a dict's own views do
    def keys(self) -> KeysView[str]:  # pyrefly: ignore[bad-override]
        return KeysView(self)

    def items(self) -> ItemsView[str, object]:  # pyrefly: ignore[bad-override]
        return ItemsView(self)

    def values(self) -> ValuesView[object]:  # pyrefly: ignore[bad-override]
        return ValuesView(self)

    def __eq__(self, other: object) -> bool:
        # equal to what a lookup finds, and to builtins' own dict, as the module's builtins are
        # in plain Python
        return self._now() == other or other == _BUILTINS

    def __ne__(self, other: object) -> bool:
        return not self == other

    __hash__ = None  # pyrefly: ignore[bad-override]

    def __repr__(self) -> str:
        return repr(self._now())

    # a union is a plain dict's, its TypeError on a non-dict included
    def __or__(self, other: object) -> object:  # pyrefly: ignore[bad-override]
        return self._now() | other  # pyrefly: ignore[unsupported-operation]

    def __ror__(self, other: object) -> object:  # pyrefly: ignore[bad-override]
        return other | self._now()  # pyrefly: ignore[unsupported-operation]

    def copy(self) -> dict[str, object]:  # pyrefly: ignore[bad-override]
        return self._now()

    def __copy__(self) -> dict[str, object]:
        return self._now()

    def __deepcopy__(self, memo: dict[int, object]) -> dict[str, object]:
        return copy.deepcopy(self._now(), memo)

    def __reduce_ex__(self, protocol: object) -> tuple[type, tuple[dict[str, object]]]:
        return (dict, (self._now(),))

    @classmethod
    def fromkeys(cls, keys: Iterable[str], value: object = None) -> dict[str, object]:  # pyrefly: ignore[bad-override]
        return dict.fromkeys(keys, value)

    def __setitem__(self, name: str, value: object) -> None:
        _BUILTINS[name] = value
        self._synced()

    def __delitem__(self, name: str) -> None:
        del _BUILTINS[name]
        self._synced()

    def update(self, *args: object, **kwargs: object) -> None:  # pyrefly: ignore[bad-override]
        _BUILTINS.update(*args, **kwargs)  # pyrefly: ignore[no-matching-overload]
        self._synced()

    def __ior__(self, other: object) -> LiveBuiltins:  # pyrefly: ignore[bad-override]
        self.update(other)
        return self

    def setdefault(self, name: str, default: object = None) -> object:  # pyrefly: ignore
        if name not in _BUILTINS:
            self[name] = default
        return self[name]

    def pop(self, name: str, *default: object) -> object:  # pyrefly: ignore[bad-override]
        value = _BUILTINS.pop(name, *default)
        self._synced()
        return value

    def popitem(self) -> tuple[str, object]:
        item = _BUILTINS.popitem()
        self._synced()
        return item

    def clear(self) -> None:
        _BUILTINS.clear()
        self._synced()


def bound_builtins() -> LiveBuiltins:
    """The builtins a module of the target's package runs with (see `LiveBuiltins`)."""
    return LiveBuiltins()

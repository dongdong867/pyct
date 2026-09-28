"""The views a tracked dict hands out: its keys, its values, and its items, each live.

Python's own views read the dict's storage in C and never call its methods, so a tracked dict
hands out views of its own. Each walks the dict as the dict's own walk does, and answers `in`
as a lookup does: a key by the lookup's fork, a value by comparing it with each value in turn,
and an item by its key's lookup and then its value's compare. Every other method of Python's
own view, the set operations on keys and items among them, is Python's answer on the dict's
storage and a downgrade named by the method, as `README.md › Rules › downgrades` says.
"""

from __future__ import annotations

import types
from collections.abc import ItemsView, Iterator, KeysView, ValuesView
from typing import Any

from pyct.core import dict_reads as reads
from pyct.core.branch import Downgrade, caller_site
from pyct.core.dict_state import DictState
from pyct.core.list_compares import matches
from pyct.core.list_state import plain
from pyct.core.values import named_as, own

# not the target's path: the view's repr and the object plumbing
_KEPT = ("__repr__", "__getattribute__", "__init__", "__sizeof__", "__new__")

# a view inherits these from object, so reading what Python's view defines never reaches them,
# and `print(config.keys())` drops the condition as `print(config)` does
_INHERITED = ("__str__", "__format__")


class _View:
    """What the three views share: the dict they read, its size, and Python's own view."""

    # the view Python's dict hands out for this one, read on the dict's storage
    python: Any = None

    def __init__(self, mapping: DictState) -> None:
        self._mapping = mapping

    @property
    def mapping(self) -> types.MappingProxyType[object, object]:
        """The dict the view reads, read-only, as Python's own view gives it."""
        return types.MappingProxyType(self._mapping)

    def __len__(self) -> int:
        """Python's `len` makes the answer plain, so it is a downgrade, but for the size a walk
        just started asks for; pyct's own `len` gives the dict's size term."""
        mapping = self._mapping
        if mapping.expression is not None and not reads.hinted(mapping):
            mapping.sink.append(Downgrade(name="__len__", site=caller_site()))
        return mapping.size()

    def __bool__(self) -> bool:
        """``if config.keys():``: the dict's own truth test, `len(config) != 0`."""
        return reads.truth(self._mapping)

    def __repr__(self) -> str:
        return repr(self.python(self._mapping))


class ConcolicKeys(_View):
    """``config.keys()``: the keys in turn, and `in` as a lookup."""

    python = staticmethod(dict.keys)
    __hash__ = None  # pyrefly: ignore[bad-override]

    def __iter__(self) -> Iterator[object]:
        return reads.walk(self._mapping, reads.key_of, "__iter__")

    def __reversed__(self) -> Iterator[object]:
        return reads.backward(self._mapping, reads.key_of, "__reversed__")

    def __contains__(self, key: object) -> bool:
        return reads.found(self._mapping, key, "__contains__")


class ConcolicValues(_View):
    """``config.values()``: the values in turn, and `in` as a compare with each."""

    python = staticmethod(dict.values)

    def __iter__(self) -> Iterator[object]:
        return reads.walk(self._mapping, reads.value_of, "__iter__")

    def __reversed__(self) -> Iterator[object]:
        return reads.backward(self._mapping, reads.value_of, "__reversed__")

    def __contains__(self, value: object) -> bool:
        """Each value in turn compared with ``value``, as Python compares them, each a fork."""
        walked = reads.walk(self._mapping, reads.value_of, "__contains__")
        return any(matches(held, value) for held in walked)


class ConcolicItems(_View):
    """``config.items()``: the pairs in turn, and `in` as a lookup and a compare."""

    python = staticmethod(dict.items)
    __hash__ = None  # pyrefly: ignore[bad-override]

    def __iter__(self) -> Iterator[object]:
        return reads.walk(self._mapping, reads.item_of, "__iter__")

    def __reversed__(self) -> Iterator[object]:
        return reads.backward(self._mapping, reads.item_of, "__reversed__")

    def __contains__(self, item: object) -> bool:
        """A pair is held when its key is, and the value there equals its value."""
        if not isinstance(item, tuple) or len(item) != 2:
            return False
        key, value = item
        mapping = self._mapping
        if not reads.found(mapping, key, "__contains__"):
            return False
        return matches(reads.value(mapping, key), value)


def _derived(name: str, python: Any) -> Any:
    """Python's own view method, run on the dict's storage: a downgrade named ``name`` while
    the dict has a form, its answer plain."""

    def downgrade(self: _View, /, *args: object, **kwargs: object) -> object:
        mapping = self._mapping
        answer = own(
            getattr(type(python(mapping)), name), python(mapping.storage()), *args, **kwargs
        )
        if answer is NotImplemented:
            return answer
        if mapping.expression is not None:
            mapping.sink.append(Downgrade(name=name, site=caller_site()))
        return _plain(answer)

    downgrade.__name__ = name
    return downgrade


def _plain(answer: object) -> object:
    """An answer Python built from the storage, with each tracked value in it plain."""
    if isinstance(answer, set | frozenset):
        return type(answer)(_plain(part) for part in answer)
    if type(answer) is tuple:
        return tuple(plain(part) for part in answer)
    return plain(answer)


def _called_on_a_value(member: object) -> bool:
    return isinstance(member, types.WrapperDescriptorType | types.MethodDescriptorType)


def _derive_and_name(cls: type[_View], registered: type) -> None:
    """Downgrade every method of Python's own view that the class body has not taught, and give
    the class the names of Python's view, which Python writes into its messages."""
    python = type(cls.python({}))
    names = {name for name, member in vars(python).items() if _called_on_a_value(member)}
    names |= set(_INHERITED)
    for name in sorted(names - set(vars(cls)) - set(vars(_View)) - set(_KEPT)):
        setattr(cls, name, _derived(name, cls.python))
    registered.register(cls)
    named_as(cls, python)


_derive_and_name(ConcolicKeys, KeysView)
_derive_and_name(ConcolicValues, ValuesView)
_derive_and_name(ConcolicItems, ItemsView)

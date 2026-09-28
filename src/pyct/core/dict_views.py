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
from typing import Any, SupportsIndex

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


def _python_type(self: _View) -> type:
    """The class a view reports: Python's view type, read from its view of an empty dict."""
    return type(self.python({}))


def _assigned_class(self: _View, kind: object) -> None:
    """`object.__setattr__(v, "__class__", kind)`: made on Python's own view of an empty dict,
    which refuses it in its own words. `v.__class__ = kind` is the view's `__setattr__`'s."""
    own(setattr, self.python({}), "__class__", kind)


class _View:
    """What the three views share: the dict they read, its size, and Python's own view."""

    # Python's view type, as `isinstance`, singledispatch and a class pattern read it, as each
    # tracked class reports its base type. It reads the class and never the dict, so it
    # records nothing. `type(v)` still reads the real class, which is how pyct tells a view
    # apart; the `type` router answers Python's view type in the target's package
    # (read-a-dict-view-s-type-as-python-s)
    __class__ = property(_python_type, _assigned_class)  # pyrefly: ignore[bad-override]

    # the view Python's dict hands out for this one, read on the dict's storage
    python: Any = None
    # the dict the view reads
    _mapping: DictState

    def __init__(self, mapping: DictState) -> None:
        # the view refuses a set, as Python's does, so pyct writes the dict by object's own set,
        # which keeps the field where Python reads it fastest; `self.__dict__` would move it
        object.__setattr__(self, "_mapping", mapping)

    def __setattr__(self, name: str, value: object, /) -> None:
        """`v.name = value`: made on Python's own view of an empty dict, which takes no
        attribute, so Python refuses it in its own words, `_mapping` too, and nothing is
        recorded (tracked-numbers-refuse-attributes-on-a-plain-number)."""
        own(setattr, self.python({}), name, value)

    def __delattr__(self, name: str, /) -> None:
        """`del v.name`: made on Python's own view of an empty dict, as a set is."""
        own(delattr, self.python({}), name)

    def __reduce_ex__(self, protocol: SupportsIndex, /) -> str | tuple[Any, ...]:
        """A pickle, a copy or a deep copy: asked of Python's own view of an empty dict, which
        refuses in its own words at every protocol. Nothing is written and no answer leaves
        the dict, so nothing is recorded (refuse-a-tracked-dict-view-s-pickle-as-python-does)."""
        return own(self.python({}).__reduce_ex__, protocol)

    def __reduce__(self) -> str | tuple[Any, ...]:
        """`v.__reduce__()`: asked of Python's own view of an empty dict, as a pickle is."""
        return own(self.python({}).__reduce__)

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

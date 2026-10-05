"""The concolic dict: a real dict that also knows the argument it came from and what changed.

The `ConcolicDict` body below is the taught set: lookups, `in`, `get`, stores and removals,
`popitem`, `setdefault`, `update`, `clear`, `copy`, `|` and `|=`, `==` and `!=`, the walks,
`reversed`, the truth test, and the three views, each followed as
follow-lists-and-dicts-as-they-change says. What is left to dict on purpose is named in
`_KEPT`, and the derivation at the bottom of the file downgrades every other method dict
defines, and the `__str__` and `__format__` it inherits from object.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Iterator
from typing import Any

from pyct.core import dict_changes as changes
from pyct.core import dict_reads as reads
from pyct.core.branch import Downgrade, Expression, caller_site
from pyct.core.dict_state import MISSING, DictState
from pyct.core.dict_views import ConcolicItems, ConcolicKeys, ConcolicValues
from pyct.core.escapes import lost
from pyct.core.list_compares import matches
from pyct.core.list_state import enter_kind, plain
from pyct.core.values import (
    REPORTED_CLASS,
    as_base,
    built_plainly,
    downgrade_the_rest,
    forked,
    own,
    refused_delete,
    refused_set,
)

# not the target's path: `__repr__`, the object plumbing, and `__init__`, which a target calls
# only to fill the dict anew, a change made without the methods that the next operation notices
_KEPT = ("__repr__", "__getattribute__", "__init__", "__sizeof__", "__class_getitem__")

# dict inherits these from object, so reading what dict itself defines never reaches them, and
# `print(config)` still drops the condition
_INHERITED = ("__str__", "__format__")


def _taking(
    python: Callable[..., object], least: int, most: int, taught: Callable[..., object]
) -> Any:
    """A taught method that takes ``least`` to ``most`` arguments and no keywords, as dict's
    does: any other call is dict's own, which refuses it in Python's words."""

    def method(self: DictState, /, *args: object, **kwargs: object) -> object:
        if kwargs or not least <= len(args) <= most:
            return own(python, self, *args, **kwargs)
        return taught(self, *args)

    return method


def _item(self: DictState, key: object) -> object:
    """``config[key]``: the lookup's fork, then the value or Python's KeyError."""
    return reads.looked_up(self, key, "__getitem__")


def _get(self: DictState, key: object, default: object = None) -> object:
    """``config.get(key, default)``: the lookup's fork, then the value or the default."""
    return reads.looked_up(self, key, "get", default)


def _contains(self: DictState, key: object) -> bool:
    """``key in config``: one fork, recorded where the `in` runs."""
    return reads.found(self, key, "__contains__")


def _pop(self: DictState, key: object, *default: object) -> object:
    """``config.pop(key[, default])``: the lookup's fork, before Python may raise KeyError."""
    return changes.removed(self, key, "pop", *default)


def _delete(self: DictState, key: object) -> None:
    """``del config[key]``: the lookup's fork, before Python may raise KeyError."""
    changes.removed(self, key, "__delitem__")


def _assign(self: DictState, key: object, value: object) -> None:
    """``config[key] = value``: whether the argument held the key, then the store."""
    changes.store(self, key, value, "__setitem__")


def _update(self: DictState, *args: Any, **kwargs: Any) -> None:
    """``config.update(...)``: each pair stored in turn, each key looked up first."""
    changes.update(self, "update", *args, **kwargs)


def _merged(self: DictState, other: object) -> object:
    """``config | other``: a tracked dict of the same argument, ``other``'s pairs stored in it."""
    return changes.merged(self, other)


def _merged_after(self: DictState, other: object) -> object:
    """``other | config``: ``other``'s keys first, the dict's values winning."""
    return changes.merged(self, other, reflected=True)


def _ior(self: DictState, other: object) -> DictState:
    """``config |= other``: each pair stored in turn, as `update` stores them."""
    changes.update(self, "__ior__", other)
    return self


def _copied(self: DictState) -> object:
    """``config.copy()`` and ``copy.copy(config)``: a tracked dict of the same argument."""
    if not self.holds("copy"):
        return own(dict.copy, self)
    return self.derived(self.storage())


def _deep_copied(self: DictState, memo: dict[int, object]) -> object:
    """``copy.deepcopy(config)``: a tracked dict of the same argument over copies of its values.

    Every key is checked first, since the copy's own shadow is the copies it makes.
    """
    followed = self.holds("__deepcopy__", *dict.keys(self))
    made: dict[object, object] = self.derived({}) if followed else {}
    memo[id(self)] = made
    items = {
        copy.deepcopy(key, memo): copy.deepcopy(value, memo) for key, value in dict.items(self)
    }
    dict.update(made, items)
    if isinstance(made, DictState):
        made.__dict__["shadow"] = dict(items)
    return made


def _equal(self: DictState, other: object) -> object:
    """``config == other`` with a dict: the sizes first, then each key and its value in turn.

    The keys are those of the plain dict, or of this one when both are tracked. Any other value
    is NotImplemented, as it is for dict.
    """
    if not isinstance(other, dict):
        return NotImplemented
    if not self.holds("__eq__"):
        return own(dict.__eq__, self.storage(), _plain_side(other))
    theirs: Expression = dict.__len__(other)
    tracked = isinstance(other, DictState) and other.holds("__eq__")
    if isinstance(other, DictState) and tracked:
        theirs = other.size_term()
    same = self.size() == dict.__len__(other)
    if not forked(self.sink, ["==", self.size_term(), theirs], same, "__eq__"):
        return False
    if isinstance(other, DictState) and tracked:
        return _pairs_match(self, other, dict.keys(self))
    return _pairs_match(other, self, dict.keys(other))


def _pairs_match(keyed: dict[object, object], tracked: DictState, keys: Any) -> bool:
    """Whether the tracked dict holds each of ``keyed``'s keys, with an equal value there: each
    lookup and each compare a fork."""
    for key in list(keys):
        if not reads.found(tracked, key, "__eq__"):
            return False
        if not matches(reads.value(tracked, key), dict.__getitem__(keyed, key)):
            return False
    return True


def _plain_side(other: dict[object, object]) -> dict[object, object]:
    """The other side of a compare Python answers: its storage, read in C."""
    return dict(dict.items(other))


def _unequal(self: DictState, other: object) -> object:
    answer = _equal(self, other)
    return answer if answer is NotImplemented else not answer


def _size(self: DictState) -> int:
    """``config.__len__()``: Python's `len` makes the answer plain before the target sees it, so
    it is a downgrade, but for the size a walk just started asks for (see `reads.hinted`). A
    `len(config)` in the target's package asks pyct's own `len`, which gives the size term."""
    if self.expression is not None and not reads.hinted(self):
        lost(self.sink, Downgrade(name="__len__", site=caller_site()))
    return self.size()


def _pickled(self: DictState, protocol: object) -> object:
    """A pickle of a tracked dict holds the plain dict: pickle-holds-the-plain-value."""
    if self.expression is not None:
        lost(self.sink, Downgrade(name="__reduce_ex__", site=caller_site()))
    return (dict, ({key: plain(value) for key, value in dict.items(self)},))


def _walked(self: DictState) -> Iterator[object]:
    return reads.walk(self, reads.key_of, "__iter__")


def _backward(self: DictState) -> Iterator[object]:
    return reads.backward(self, reads.key_of, "__reversed__")


class ConcolicDict(DictState):
    """A real dict with the argument it came from, a sink, and a shadow of what pyct saw.

    The operations taught below stay symbolic. Any other method dict defines, except those left
    to it in `_KEPT`, is dict's own and returns a plain value, with a downgrade in the sink
    naming what was lost (``README.md › Rules › downgrades``).
    """

    # the base type, as `isinstance`, singledispatch and a class pattern read it; the class
    # called with a value is dict's own, a plain dict, since pyct builds one through `made`
    __class__ = REPORTED_CLASS  # pyrefly: ignore[bad-override]
    __new__ = as_base
    # a plain dict takes no attribute: a set or a delete is Python's own refusal, pyct's names too
    __setattr__ = refused_set
    __delattr__ = refused_delete

    # the lookups, each recording whether the key is there the first time the path asks
    __getitem__ = _item  # pyrefly: ignore[bad-override]
    get = _taking(dict.get, 1, 2, _get)
    __contains__ = _contains  # pyrefly: ignore[bad-override]
    __bool__ = reads.truth
    __len__ = _size

    # the walks and the views, each key in insertion order
    __iter__ = _walked  # pyrefly: ignore[bad-override]
    __reversed__ = _backward  # pyrefly: ignore[bad-override]
    keys = _taking(dict.keys, 0, 0, ConcolicKeys)
    values = _taking(dict.values, 0, 0, ConcolicValues)
    items = _taking(dict.items, 0, 0, ConcolicItems)

    # the compares, a key and its value at a time
    __eq__ = _equal  # pyrefly: ignore[bad-override]
    __ne__ = _unequal  # pyrefly: ignore[bad-override]
    __hash__ = None

    # the dicts it builds, each tracked with the argument it came from
    copy = _taking(dict.copy, 0, 0, _copied)
    __copy__ = _copied
    __deepcopy__ = _deep_copied
    __or__ = _merged  # pyrefly: ignore[bad-override]
    __ror__ = _merged_after  # pyrefly: ignore[bad-override]
    __reduce_ex__ = _pickled  # pyrefly: ignore[bad-override]
    fromkeys = built_plainly(dict, "fromkeys")

    # the changes, each noting what the dict holds after it
    __setitem__ = _assign  # pyrefly: ignore[bad-override]
    __delitem__ = _delete  # pyrefly: ignore[bad-override]
    __ior__ = _ior  # pyrefly: ignore[bad-override]
    pop = _taking(dict.pop, 1, 2, _pop)
    popitem = _taking(dict.popitem, 0, 0, changes.last_item)
    setdefault = _taking(dict.setdefault, 1, 2, changes.defaulted)
    update = _update  # pyrefly: ignore[bad-override]
    clear = _taking(dict.clear, 0, 0, changes.emptied)


# the class body above is everything ConcolicDict teaches. The rest of dict, and the `__str__`
# and `__format__` it inherits, differ only in the name they call and record, so the derivation
# writes them
downgrade_the_rest(ConcolicDict, dict, kept=_KEPT, inherited=_INHERITED)
enter_kind(ConcolicDict, "dict")

__all__ = ["MISSING", "ConcolicDict"]

"""How a tracked dict changes: each change Python makes, and what the dict notes of it.

Every change looks the key up first, as a lookup does, so the fork on whether the argument held
the key is recorded before Python may raise KeyError, and the change's effect on the size is
known. Python then makes the change through `own`, so what it takes, refuses and raises is its
own, and the dict notes it in its shadow and in ``changed``.

A change under a tracked key of the dict's own key kind is followed as one under a literal: its
lookup records whether the key equals each key changed before and then whether the argument
holds it (``dict_reads.after_changes``), so the path settles which key it changes, and the dict
changes the key's plain value and logs the change under the key's expression.

A change under a key pyct does not follow, a tracked bool or float, a tracked key of the other
kind, or a key of another kind, is Python's own and a downgrade named by the operation; the dict
notes what it did to that key, as the plain key it is, so the forks after it still read the
dict's size. Storing a value no expression holds, anything but an int, str, float, bool, None,
or a list or dict of those, is a downgrade too, and the dict is plain from then on.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pyct.core.bools import ConcolicBool
from pyct.core.branch import Branch, Downgrade, Expression, caller_site
from pyct.core.dict_reads import (
    POPPED,
    found,
    handed_in_place,
    handout,
    int_key,
    is_tracked,
    may_equal_added,
    placed,
    present,
    recorded,
    value,
    written_key,
)
from pyct.core.dict_state import MISSING, DictState
from pyct.core.floats import ConcolicFloat
from pyct.core.ints import ConcolicInt
from pyct.core.list_state import plain
from pyct.core.strs import ConcolicStr
from pyct.core.values import own

# the values an expression holds as they are, tracked or plain: JSON reads each back
_HELD: tuple[type, ...] = (
    int,
    str,
    float,
    bool,
    type(None),
    ConcolicInt,
    ConcolicStr,
    ConcolicFloat,
    ConcolicBool,
)


def holdable(value: object) -> bool:
    """Whether an expression can hold a value: a plain or tracked int, str, float, bool or None,
    or a list or dict of those, walked on a stack of its own so no depth recurses."""
    seen: set[int] = set()
    stack = [value]
    while stack:
        part = stack.pop()
        if type(part) in _HELD:
            continue
        if not isinstance(part, list | dict):
            return False
        if id(part) not in seen:
            seen.add(id(part))
            stack.extend(dict.values(part) if isinstance(part, dict) else list.copy(part))
    return True


def plain_key(key: object) -> bool:
    """Whether ``key`` is a plain str or int, a literal a fork writes."""
    return type(key) is str or type(key) is int


def followed(self: DictState, key: object) -> bool:
    """Whether a change under ``key`` is followed: a plain str or int, or a tracked key of the
    kind the dict's keys are, an int under `dict[int, X]` and a str elsewhere."""
    return plain_key(key) or type(key) is (ConcolicInt if self.int_keyed else ConcolicStr)


def _joined_key(self: DictState, made: DictState, key: object, before: list[object]) -> None:
    """One of ``other``'s keys in ``other | config``, looked up in the dict: a key it does not
    hold is one ``made`` adds. ``before`` holds ``other``'s keys the dict follows so far."""
    looked = int_key(key)
    if followed(self, looked):
        _apart(self, looked, before)
        before.append(looked)
        held = looked_up_to_change(self, looked, "__ror__")
        tracked, away = under(looked), apart(self, looked, held)
    else:
        held = bool(as_python(self, key, "__ror__", lambda: dict.__contains__(self, key)))
        tracked, away = None, False
    if not held:
        made.logged(plain(looked), True, tracked, apart=away)
        made.grown += 1


def _apart(self: DictState, key: object, before: list[object]) -> None:
    """Record that a key of ``other | config`` is none of ``other``'s keys before it, where
    either is tracked: Python built ``other`` with its keys apart, which the answer keeps."""
    bare = plain(key)
    for earlier in before:
        if type(plain(earlier)) is type(bare) and (is_tracked(key) or is_tracked(earlier)):
            pair = (key, earlier) if is_tracked(key) else (earlier, key)
            fork = ["==", written_key(pair[0]), written_key(pair[1])]
            recorded(self, Branch(fork, False, caller_site(), False, "__ror__"))


def followed_tracked(self: DictState, key: object) -> bool:
    """Whether ``key`` is a tracked key a change under it follows (see ``followed``)."""
    return is_tracked(key) and followed(self, key)


def under(key: object) -> Expression:
    """The expression a change under ``key`` is logged by: a tracked key's, None for a plain."""
    return key.expression if isinstance(key, ConcolicStr | ConcolicInt) else None


def looked_up_to_change(self: DictState, key: object, name: str) -> bool:
    """A followed change's lookup, recorded before the change: whether the dict holds the key.
    A tracked key the argument does not hold is the target's own for a walk (see
    ``dict_reads.placed``), as a plain one is."""
    held = bool(present(self, key, name, changing=True))
    if is_tracked(key) and plain(key) not in self.changed:
        self.settled.setdefault(plain(key), held)
    return held


def apart(self: DictState, key: object, held: bool) -> bool:
    """Whether a change's lookup found a tracked key apart from every key of the argument: no
    change before it decided the lookup, and the argument does not hold it."""
    return is_tracked(key) and plain(key) not in self.changed and not held


def holds_key(self: DictState, key: object, name: str) -> bool:
    """Whether the form still describes the dict, reading ``key``'s slot only when the key is
    one a fork can write, so a key Python cannot hash raises in Python's own call."""
    if written_key(key) is None:
        return self.holds(name)
    return self.holds(name, plain(key))


def as_python(
    self: DictState, key: object, name: str, change: Callable[[], object], *, named: bool = False
) -> object:
    """A change under a key pyct does not follow: Python's own, and a downgrade named ``name``,
    with whether the key was there noted from the dict itself, so the size stays the dict's.
    ``named`` says the call's own lookup already named it, so the call is named once. A key
    that may equal an int key the solver adds turns the dict plain (see ``may_equal_added``)."""
    bare = plain(key)
    held = own(dict.__contains__, self, bare)
    answer = own(change)
    if not named:
        self.sink.append(Downgrade(name=name, site=caller_site()))
    if bare not in self.changed:
        self.settled.setdefault(bare, held)
    if may_equal_added(self, key):
        self.turn_plain()
    return answer


def looked_up_as_python(self: DictState, key: object) -> bool:
    """Whether a lookup of ``key`` names its call as a downgrade: a tracked key into a dict the
    target changed, which no expression writes whole."""
    return is_tracked(key) and bool(self.changed)


def store(self: DictState, key: object, stored: object, name: str, *, named: bool = False) -> None:
    """``config[key] = value``, and each store `setdefault`, `update` and `|` make. ``named``
    says the call's own lookup already named it (see ``as_python``). A key Python's lookup
    makes the same as an int is looked up as that int, and stored as it is."""
    looked = int_key(key)
    bare = plain(looked)
    if not holds_key(self, key, name):
        own(dict.__setitem__, self, key, stored)
        return
    if not holdable(stored):
        own(dict.__setitem__, self, key, stored)
        self.lose(name)
        return
    if followed(self, looked):
        held = looked_up_to_change(self, looked, name)
        away = apart(self, looked, held)
        own(dict.__setitem__, self, bare if is_tracked(looked) else key, stored)
        self.noted(bare, stored, under(looked), apart=away)
        return
    as_python(self, key, name, lambda: dict.__setitem__(self, bare, stored), named=named)
    self.noted(bare, stored)


def removed(self: DictState, key: object, name: str, *default: object) -> object:
    """``del config[key]`` and ``pop``: the lookup's fork first, then the value it hands out.

    A key the dict does not hold raises KeyError where Python does, after its fork, or hands
    back the default. A tracked key of the dict's key kind is followed as a literal is; one of
    another kind is looked up as any lookup is, and the removal itself is a downgrade.
    """
    if not holds_key(self, key, name):
        return own(dict.pop, self, key, *default)
    looked = int_key(key)
    if written_key(looked) is None:
        return _removed_as_python(self, key, name, default)
    follow = followed(self, looked)
    named = looked_up_as_python(self, key)
    if not found(self, key, name, raising=not default, changing=follow):
        return default[0] if default else own(dict.__getitem__, self, plain(key))
    handed = value(self, key, changing=follow)
    bare = plain(looked)
    if follow:
        own(dict.__delitem__, self, bare)
        self.dropped(bare, under(looked))
        return handed
    as_python(self, key, name, lambda: dict.__delitem__(self, bare), named=named)
    self.dropped(bare)
    return handed


def _removed_as_python(
    self: DictState, key: object, name: str, default: tuple[object, ...]
) -> object:
    """A removal under a key of another kind: Python's own, named ``name``."""
    held = own(dict.__contains__, self, key)
    answer = as_python(self, key, name, lambda: dict.pop(self, key, *default))
    if held:
        self.dropped(key)
    return answer


def last_item(self: DictState) -> tuple[object, object]:
    """``config.popitem()``: whether the dict holds anything, recorded before KeyError, and then
    its last key and value, handed out as a walk from the end hands them."""
    if not self.holds("popitem"):
        return own(dict.popitem, self)
    key = next(reversed(dict.keys(self)), MISSING)
    pin = None if key is MISSING else placed(self, key, POPPED)
    fork = Branch(
        ["!=", self.size_term(), 0], key is not MISSING, caller_site(), True, "popitem", pin
    )
    if not recorded(self, fork):
        return own(dict.popitem, self)
    if not self.holds("popitem", key):
        return own(dict.popitem, self)
    handed_in_place(self, key, "popitem", pin)
    handed = dict.__getitem__(self, key)
    own(dict.__delitem__, self, key)
    self.dropped(key)
    # the key a walk handed out for it, so a walk and popitem hand out one object, as in Python
    return handout(self, key, None), handed


def defaulted(self: DictState, key: object, default: object = None) -> object:
    """``config.setdefault(key, default)``: the value when the dict holds the key, else a store."""
    if not holds_key(self, key, "setdefault"):
        return own(dict.setdefault, self, key, default)
    if written_key(int_key(key)) is None:
        held = own(dict.__contains__, self, key)
        answer = as_python(self, key, "setdefault", lambda: dict.setdefault(self, key, default))
        if not held:
            self.noted(key, default)
        return answer
    follow = followed(self, int_key(key))
    named = looked_up_as_python(self, key) and not follow
    if found(self, key, "setdefault", changing=follow):
        return value(self, key, changing=follow)
    store(self, key, default, "setdefault", named=named)
    return default


def update(self: DictState, name: str, *args: Any, **kwargs: Any) -> None:
    """``config.update(...)`` and ``config |= ...``: each pair Python reads, stored in turn.

    Python reads a mapping by its keys and each value under one, and anything else as pairs;
    it is read once, into a plain dict, so what it takes and refuses is Python's own.
    """
    taken: dict[object, object] = {}
    own(dict.update, taken, *args, **kwargs)
    for key, stored in dict.items(taken):
        store(self, key, stored, name)


def emptied(self: DictState) -> None:
    """``config.clear()``: the dict is ``{}``, a plain dict, and nothing of the input is in it."""
    dict.clear(self)
    self.shadow = {}
    self.expression = None


def merged(self: DictState, other: object, *, reflected: bool = False) -> object:
    """``config | other``, or ``other | config`` when ``reflected``, with a dict ``other``: a
    tracked dict of the same argument, each key of ``other`` looked up in it first.

    Any other value is NotImplemented, as it is for dict. The keys come in Python's own order,
    and where both hold a key the right one's value wins, as Python's does.
    """
    name = "__ror__" if reflected else "__or__"
    if not isinstance(other, dict):
        return NotImplemented
    if not self.holds(name):
        return own(dict.__or__, *((other, self) if reflected else (self, other)))
    if reflected:
        return _joined_after(self, dict(dict.items(other)))
    made = self.derived(self.storage())
    update(made, name, other)
    return made


def _joined_after(self: DictState, other: dict[object, object]) -> object:
    """``other | config``: ``other``'s keys first, the dict's values winning, each of ``other``'s
    keys looked up in the dict so the size is known, until a key the dict cannot follow turns
    it plain, and then the dict built from it too. A tracked key it follows goes in as its
    plain value, as a store puts it, so no key Python compares later is a tracked one."""
    keyed = {
        plain(key) if followed_tracked(self, key) else key: held for key, held in other.items()
    }
    made = self.derived({**keyed, **self.storage()})
    before: list[object] = []
    for key in other:
        if self.expression is None:
            # a key the dict could not follow turned it plain: it records nothing more
            break
        _joined_key(self, made, key, before)
    if self.expression is None:
        # the dict built holds the key that turned this one plain, so it cannot be followed either
        made.turn_plain()
    return made

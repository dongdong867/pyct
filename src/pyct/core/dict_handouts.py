"""What a walk of a tracked dict hands out: its own copy of each key, where it read the key, and
what a later lookup of that copy knows (containers-arrays-counted-keys-and-copied-walk-keys).

A copy no code can write proves its key was there when the walk handed it out. A change under a
tracked key that may touch a held key makes the copies stale: their lookups ask again, given
where the walk read the key, and a copy of the target's own key stands for the tracked key it
was stored under. A key Python shares has no copy, so after a change under a tracked key it
runs as where that change is Python's own (``dict_compares.shared_after_tracked``).
"""

from __future__ import annotations

from pyct.core.branch import Expression
from pyct.core.dict_compares import own_key, stored_under
from pyct.core.dict_state import MISSING, DictState
from pyct.core.ints import ConcolicInt
from pyct.core.strs import ConcolicStr

# the end a walk starts from, which says what keeps a key it reads at its place, and popitem's,
# which reads the last key and removes it
FIRST, LAST, POPPED = "walked", "last", "popped"


def proven(self: DictState, key: object) -> bool:
    """Whether the key is the very object a walk of this dict handed out, whenever the walk ran,
    as in `for k in sorted(d): d[k]` or Python's own `dict(d)`: the dict held it when the walk
    handed it out, and a change under a plain key since moved it alike for every input, so no
    input takes the other side of the lookup. A change under a tracked key that may touch a
    held key makes every copy stale (see ``DictState.logged``), since the solver may make that
    key this one; a later walk hands out a new copy. A walk hands out a
    copy of each key no code can write, so a key the target writes as a literal is looked up as
    any other. A walk hands out only a plain str or int, so any other key, a tracked one among
    them, is never one: it is refused before it is hashed, which on a tracked key would compare
    it with a stored key and record a fork."""
    if type(key) is not str and type(key) is not int:
        return False
    return self.copies.get(key, MISSING) is key


def handout(self: DictState, key: object, pin: Expression) -> object:
    """The key a walk hands out for a stored key: its own copy, the same for every walk until a
    change makes it stale, and where the walk read it.

    A key Python shares, a one-character str, the empty str or a small int, has no copy: a
    literal the target writes is the same object. Its lookup holds where the walk read it
    (``pin``), so its other side is asked with that place and without it.
    """
    if type(key) is not str and type(key) is not int:
        # a key of another kind is never copied, so it is hashed no more than Python hashes it
        return key
    copied = self.copies.get(key, MISSING)
    if copied is MISSING:
        # a new copy: one a change made stale stays stale, whatever this walk reads
        copied = copy_of(key)
        if copied is not key:
            self.copies[key] = copied
    if copied is key:
        if pin is not None:
            self.shared[key] = pin
        return copied
    under = stored_under(self, key) if own_key(self, key) else None
    self.handed[id(copied)] = (copied, pin, under)
    return copied


def copy_of(key: object) -> object:
    """A new object equal to a str or int key, or the key itself where Python shares one."""
    if type(key) is str and len(key) > 1:
        return "".join([key[:1], key[1:]])
    if type(key) is int:
        return int.__add__(int.__add__(key, 1), -1)
    return key


def _stale(self: DictState, key: object) -> tuple[object, Expression, Expression] | None:
    """What a walk handed out a stale copy with, when ``key`` is that copy: the copy, where the
    walk read its key, and the tracked key a key of the target's own was stored under."""
    entry = self.handed.get(id(key)) if id(key) in self.stale else None
    return entry if entry is not None and entry[0] is key else None


def stand_in(self: DictState, key: object) -> object:
    """``key``, or the tracked key a stale copy of the target's own key was stored under, as a
    key of its value and that key's expression: on another input the walk handed out that
    key's value in its place, so its lookup and a change under it are that key's. A key Python
    shares has no copy, and the target may write it too, so it stands for itself."""
    entry = _stale(self, key)
    under = None if entry is None else entry[2]
    if under is None:
        return key
    if isinstance(key, str):
        return ConcolicStr.made(key, under, self.sink)
    assert isinstance(key, int)
    return ConcolicInt.made(key, under, self.sink)


def given_place(self: DictState, key: object) -> Expression:
    """Where a walk read a key whose lookup holds there whatever a fork reads, or None: a key
    Python shares, which no copy stands for, and a copy a change made stale (see
    ``DictState.logged``)."""
    if type(key) is not str and type(key) is not int:
        return None
    entry = _stale(self, key)
    return self.shared.get(key) if entry is None else entry[1]


def walked_in_the_argument(self: DictState, key: object) -> bool:
    """Whether ``key`` is a stale copy of a key a walk read in the argument: the place the walk
    read it at, which its lookup is given, says the argument holds it (see ``given_place``)."""
    entry = _stale(self, key)
    pin = None if entry is None else entry[1]
    return isinstance(pin, list) and pin[0] in (FIRST, LAST)

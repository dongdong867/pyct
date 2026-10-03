"""How a tracked dict is read: whether it holds a key, the value under one, and a walk.

Every lookup records whether the key is there, where it runs, the first time the path asks
about that key: `["in", "'port'", config]`. After that the path settles the answer, and a later
lookup of that key is a fact of the path, not a fork (``core.branch.Fact``). A key the target
stored or removed is known, and one a walk handed out was there. A key is a plain str or int,
written as a literal, or a tracked one, written as its expression, which the solver may change;
a tracked key into a dict the target changed is Python's own answer and a downgrade, since no
expression writes the dict whole.

A walk over the keys, the values or the items records `[">", size, j]` for each key it takes
and once more, taken false, where it ends, in insertion order. A pass the dict's fewest keys
reach (``DictState.fewest``) is a fact, not a fork. Each key it hands out is plain, and each
value as the dict holds it: an argument's value tracked, the target's own as it is. A walk is
not a lookup, so it settles nothing; after each pass it records a fact of which key it read at
its place (``placed``), so an answer keeps that key there, as a read keeps a list's item. It
hands out its own copy of each key, so a lookup of that very object, whenever it runs, is one no
input fails and records no fork (``proven``); a key Python shares with the target's literals has
no copy, and its lookup records the place the walk read it first (``handout``).

`len(config)` and `bool(config)` where pyct binds or routes them, and on each of its views, read
the size term, `["len", config]` and what the target added or removed, and record no fork where
they run. A truth test of a dict whose fewest keys are above zero is a fact, not a fork.
"""

from __future__ import annotations

import json
import numbers
from collections.abc import Callable, Iterator
from typing import Any

from pyct.core.bools import ConcolicBool
from pyct.core.branch import Branch, Downgrade, Expression, Fact, caller_site
from pyct.core.dict_state import MISSING, TRACKED, DictState
from pyct.core.ints import ConcolicInt
from pyct.core.list_reads import caller
from pyct.core.list_state import plain
from pyct.core.strs import ConcolicStr
from pyct.core.values import forked, own

# what a walk hands out for each key: the key, its value, or both
type Pick = Callable[[DictState, object], object]


def written_key(key: object) -> Expression | None:
    """A key as a fork writes it: a str in its Python quotes, an int as itself, a tracked one by
    its expression. None for a key of any other kind, which pyct does not follow."""
    if type(key) is str:
        return str.__repr__(key)
    if type(key) is int:
        return int.__int__(key)
    if type(key) is ConcolicStr or type(key) is ConcolicInt:
        return key.expression
    return None


def int_key(key: object) -> object:
    """The int a plain key equals and hashes as, which makes Python's lookup of it that int's:
    an integral float, or a bool or other int subclass that keeps int's `__eq__` and
    `__hash__`, an IntEnum member among them. Any other key as it is."""
    kind = type(key)
    if isinstance(key, float) and kind is float:
        return int(key) if key.is_integer() else key
    if kind is int or not isinstance(key, int) or kind is ConcolicInt or kind is ConcolicBool:
        return key
    if kind.__eq__ is int.__eq__ and kind.__hash__ is int.__hash__:
        return int.__int__(key)
    return key


def looked_up_unfollowed(self: DictState, key: object, name: str) -> None:
    """Name a lookup pyct does not follow as a downgrade, and turn the dict plain where the key
    may equal an int key the solver adds (see ``may_equal_added``)."""
    if may_equal_added(self, key):
        self.lose(name)
    else:
        self.sink.append(Downgrade(name=name, site=caller_site()))


def may_equal_added(self: DictState, key: object) -> bool:
    """Whether a key pyct does not follow may equal an int key the solver adds, one a fork
    names or one pyct makes up, which that key's lookup does not name: in a ``dict[int, X]``,
    any number but a plain float that is not integral, a tracked bool or float, a Fraction, a
    Decimal or an int with its own `__hash__` among them, and any key whose `==` is its own."""
    if not self.int_keyed or written_key(int_key(key)) is not None:
        return False
    if type(key) is float:
        # a plain float here is not integral, and never equals an int
        return False
    bare = plain(key)
    return isinstance(bare, numbers.Number) or type(bare).__eq__ not in _APART_FROM_INTS


# the `==` of str, bytes, tuple, frozenset and None, whose values never equal an int, and
# object's, which is `is`
_APART_FROM_INTS = frozenset(
    kind.__eq__ for kind in (object, str, bytes, tuple, frozenset, type(None))
)


def is_tracked(key: object) -> bool:
    """Whether a key is a tracked str or int, which the solver may change."""
    return type(key) is ConcolicStr or type(key) is ConcolicInt


def settled_as(key: object) -> object:
    """What ``settled`` knows a key by: a plain key as itself, a tracked one by its expression."""
    if is_tracked(key):
        assert isinstance(key, ConcolicStr | ConcolicInt)
        return ("tracked", json.dumps(key.expression))
    return key


def present(self: DictState, key: object, name: str, *, raising: bool = False) -> bool | None:
    """Whether the dict holds ``key``, recording the fork the first time the path asks, which
    settles the answer: a later lookup of the same key, with no change under it since, is a
    fact that holds what the first found. On a dict changed without a fork no lookup is a
    fact, since that change may have touched the key on another input: one recorded here is a
    fork, and a key the target changed or a walk handed out is answered without either.

    A key Python shares with the target's literals that a walk handed out keeps the place the
    walk read it, given by the lookup: a fact recorded before the fork, which holds on both its
    sides.

    None when pyct does not follow this lookup, which the caller answers as Python does and
    names as a downgrade: a key of another kind, or a tracked key into a dict the target
    changed. Python's own lookup compares a key it finds with `==`, which on a tracked key
    records a fork no target wrote, so every lookup here reads the key's plain value.
    """
    held = dict.__contains__(self, plain(key))
    written = written_key(key)
    if written is None or (is_tracked(key) and self.changed):
        return None
    known = settled_as(key)
    if plain(key) in self.changed or proven(self, key):
        return held
    given = self.shared.get(key) if type(key) in (str, int) else None
    place: Expression = None if given is None else ["given", given]
    test = ["in", written, self.expression]
    site = caller_site()
    self.settled.setdefault(known, held)
    # after a change without a fork, a lookup recorded here is a fork, and adds nothing to the
    # keys asked and found that the argument's other dicts decide by; ``settled``, shared too,
    # is still noted
    if not self.unforked:
        if known in self.asked:
            self.sink.append(Fact(test, held, site, raising, place, lost_as=name))
            return held
        self.asked.add(known)
        if held:
            self.found.add(TRACKED if is_tracked(key) else known)
    if place is not None:
        self.sink.append(Fact(None, True, site, raising, place, lost_as=name))
    return recorded(self, Branch(test, held, site, raising, name))


def recorded(self: DictState, branch: Branch) -> bool:
    """Record a fork, and answer with the side it took."""
    self.sink.append(branch)
    return branch.taken


def proven(self: DictState, key: object) -> bool:
    """Whether the key is the very object a walk of this dict handed out, whenever the walk ran,
    as in `for k in sorted(d): d[k]` or Python's own `dict(d)`: the dict held it when the walk
    handed it out, and no store or removal since (``changed``) moved it, so no input takes the
    other side of the lookup. A walk hands out a copy of each key no code can write, so a key
    the target writes as a literal is looked up as any other. A walk hands out only a plain str
    or int, so any other key, a tracked one among them, is never one: it is refused before it
    is hashed, which on a tracked key would compare it with a stored key and record a fork."""
    if type(key) is not str and type(key) is not int:
        return False
    return self.copies.get(key, MISSING) is key


def handout(self: DictState, key: object, pin: Expression) -> object:
    """The key a walk hands out for a stored key: its own copy, the same for every walk.

    A key Python shares, a one-character str or a small int, has no copy: a literal the target
    writes is the same object. Its lookup is recorded as any other, and holds where the walk
    read it (``pin``), so its other side is asked with that place and without it.
    """
    if type(key) is not str and type(key) is not int:
        # a key of another kind is never copied, so it is hashed no more than Python hashes it
        return key
    copied = self.copies.get(key, MISSING)
    if copied is MISSING:
        copied = _copy(key)
        if copied is not key:
            self.copies[key] = copied
    if copied is key and pin is not None:
        self.shared[key] = pin
    return copied


def _copy(key: object) -> object:
    """A new object equal to a str or int key, or the key itself where Python shares one."""
    if type(key) is str and len(key) > 1:
        return "".join([key[:1], key[1:]])
    if type(key) is int:
        return int.__add__(int.__add__(key, 1), -1)
    return key


def found(self: DictState, key: object, name: str, *, raising: bool = False) -> bool:
    """Whether the dict holds ``key``, answered and recorded where pyct follows the lookup, and
    otherwise Python's answer, named ``name``: a key of another kind is Python's to hash."""
    looked = int_key(key)
    if written_key(looked) is None:
        # a tracked key's plain value, so Python's lookup records no `==` the target never wrote
        answer = own(dict.__contains__, self, plain(key))
        if self.expression is not None:
            looked_up_unfollowed(self, key, name)
        return answer
    bare = plain(looked)
    if not self.holds(name, bare):
        return dict.__contains__(self, bare)
    answer = present(self, looked, name, raising=raising)
    if answer is None:
        self.sink.append(Downgrade(name=name, site=caller_site()))
        return dict.__contains__(self, bare)
    return answer


def value(self: DictState, key: object) -> object:
    """The value under a key the dict holds, handed out as the target reads it.

    A tracked key reads the argument's value as ``config[name]``, so the solver may change the
    key; any other key, and a tracked one into a dict the target changed, hands out what the
    dict holds there.
    """
    held = dict.__getitem__(self, plain(key))
    if not is_tracked(key) or self.expression is None or self.changed:
        return held
    assert isinstance(key, ConcolicStr | ConcolicInt)
    read: Expression = ["[]", self.expression, key.expression]
    stored = plain(held)
    if type(stored) is str:
        return ConcolicStr.made(stored, read, self.sink)
    if type(stored) is int:
        return ConcolicInt.made(stored, read, self.sink)
    return held


def looked_up(self: DictState, key: object, name: str, default: object = MISSING) -> object:
    """``config[key]``, or ``get`` with a default: the presence fork first, then the value.

    A key the dict does not hold raises KeyError where Python does, after its fork, or hands
    back the default.
    """
    if not found(self, key, name, raising=default is MISSING):
        if default is MISSING:
            return own(dict.__getitem__, self, plain(key))
        return default
    return value(self, key)


def length(self: DictState) -> int:
    """`len(config)` where pyct binds `len`: the dict's size, carrying its size term, the same
    term its own forks read. A dict with no form gives its plain size."""
    if not self.holds("__len__"):
        return self.size()
    return ConcolicInt.made(self.size(), self.size_term(), self.sink)


def truth(self: DictState) -> bool:
    """``if config:``: Python tests a dict by its size, so the fork is `len(config) != 0`, or a
    fact where the dict holds a key on every input that takes the path."""
    if not self.holds("__bool__"):
        return self.size() != 0
    if decided_filled(self):
        return True
    return forked(self.sink, ["!=", self.size_term(), 0], self.size() != 0)


def condition(self: DictState) -> Any:
    """`bool(config)` where pyct routes `bool`: the condition `if config:` tests, as a tracked
    bool that records no fork, so the fork is recorded where the target tests it.

    It holds the dict's size term at the call, which a later change replaces rather than edits.
    A dict with no form gives Python's plain answer; one whose form stopped describing it does
    too, naming `__bool__` as `if config:` does. A dict that holds a key on every input that
    takes the path records the fact where `bool` is called, and answers a plain True.
    """
    filled = self.size() != 0
    if not self.holds("__bool__"):
        return filled
    if decided_filled(self):
        return True
    return ConcolicBool.made(filled, ["!=", self.size_term(), 0], self.sink)


def decided_filled(self: DictState) -> bool:
    """Whether the dict holds a key on every input that takes the path, recording the truth
    test as a fact where it does."""
    if self.fewest() <= 0:
        return False
    self.sink.append(Fact(["!=", self.size_term(), 0], True, caller_site()))
    return True


def key_of(self: DictState, key: object) -> object:
    return self.copies.get(key, key)


def value_of(self: DictState, key: object) -> object:
    return dict.__getitem__(self, key)


def item_of(self: DictState, key: object) -> object:
    return self.copies.get(key, key), dict.__getitem__(self, key)


def walk(self: DictState, pick: Pick, name: str, *, depth: int = 3) -> Iterator[object]:
    """A walk over the dict from its first key: a fork or a fact per key, and a fork where it
    ends (see ``passed``).

    ``depth`` is how many calls up the code that asked for the walk sits (see ``hinted``).
    """
    self.__dict__["walked_at"] = caller(depth)
    return _walked(self, iter(dict.keys(self)), pick, (name, FIRST))


def backward(self: DictState, pick: Pick, name: str) -> Iterator[object]:
    """A walk over the dict from its last key, recording as a walk from the first does."""
    return _walked(self, reversed(dict.keys(self)), pick, (name, LAST))


# the end a walk starts from, which says what keeps a key it reads at its place, and popitem's,
# which reads the last key and removes it
FIRST, LAST, POPPED = "walked", "last", "popped"


def placed(self: DictState, key: object, end: str) -> Expression:
    """What keeps ``key`` where a walk from ``end`` read it, as the solver reads it, or None when
    nothing needs to.

    An answer lists the argument's keys in the input's order, then the keys a fork names, then
    the made-up ones. From the first, the argument's key ``k`` stays in its place when the
    input's keys up to it stay (`["walked", A, k]`), and the target's own key when the argument
    holds exactly the input's keys (`["exactly", A]`), since an added key would come before it.
    From the last, the argument's key stays last when it stays and no key is added after it
    (`["last", A, k]`); the target's own keys come after the argument's, where no answer moves
    them. A key no fork can write pins nothing.
    """
    written = written_key(key)
    if written is None:
        return None
    own_key = self.changed.get(key) is True and self.settled.get(key) is False
    if end in (LAST, POPPED):
        return None if own_key else [end, self.expression, written]
    return ["exactly", self.expression] if own_key else ["walked", self.expression, written]


def _walked(
    self: DictState, keys: Iterator[object], pick: Pick, how: tuple[str, str]
) -> Iterator[object]:
    """Each key in Python's own order: Python's own iterator raises where the dict changes size
    while it walks. A change made without the dict's methods turns the walk plain there. Each
    key is handed out as the walk's own copy of it (see ``handout``)."""
    name, end = how
    at = 0
    while True:
        key = own(next, keys, MISSING)
        if not self.holds(name, *(() if key is MISSING else (key,))):
            break
        pin = None if key is MISSING else placed(self, key, end)
        if not passed(self, at, key, pin, name):
            return
        handout(self, key, pin)
        yield pick(self, key)
        at += 1
    while key is not MISSING:
        yield plain_pick(pick, self, key)
        key = own(next, keys, MISSING)


def passed(self: DictState, at: int, key: object, pin: Expression, name: str) -> bool:
    """Record whether a walk takes pass ``at``, and answer it: a fact where the dict holds more
    than ``at`` keys on every input that takes the path, else a fork; then the place the pass
    read its key at, a fact that holds only on the side the pass took."""
    test = [">", self.size_term(), at]
    site = caller_site()
    taken = key is not MISSING
    if taken and self.fewest() > at:
        self.sink.append(Fact(test, True, site, False, pin, lost_as=name))
        return True
    if not recorded(self, Branch(test, taken, site, False, name)):
        return False
    if pin is not None:
        self.sink.append(Fact(None, True, site, False, pin, lost_as=name))
    return True


def plain_pick(pick: Pick, self: DictState, key: object) -> object:
    """What a walk hands out once the dict is plain: its items as Python holds them."""
    picked = pick(self, key)
    return tuple(plain(part) for part in picked) if isinstance(picked, tuple) else plain(picked)


def hinted(self: DictState, depth: int = 3) -> bool:
    """Whether a `__len__` call is Python's own guess at the size of a walk it just started:
    `list(config)`, `sorted` and `tuple` start a walk and then ask the size, in the same call of
    the same code. Only the first ask after a walk starts can be that guess."""
    started = self.walked_at
    self.__dict__["walked_at"] = None
    return started is not None and started == caller(depth)

"""How a tracked dict is read: whether it holds a key, the value under one, and a walk.

Every lookup records whether the key is there, where it runs, the first time the path asks
about that key: `["in", "'port'", config]`. After that the path settles the answer, and a later
lookup of that key is a fact of the path, not a fork (``core.branch.Fact``). A key the target
stored or removed is known, and one a walk handed out was there. A key is a plain str or int,
written as a literal, or a tracked one, written as its expression, which the solver may change.
After a change under a tracked key, a lookup first records whether its key equals that one
(``after_changes``). A tracked key the target looks up in a dict it changed is Python's own
answer and a downgrade; only a change under a tracked key looks it up there, and records
whether it equals each key changed before.

A walk over the keys, the values or the items records `[">", size, j]` for each key it takes
and once more, taken false, where it ends, in insertion order. A pass or an end the dict's
range proves (``DictState.measured``) is a fact, not a fork. Each key it hands out is plain, and
each value as the dict holds it: an argument's value tracked, the target's own as it is. A walk is
not a lookup, so it settles nothing; after each pass it records a fact of which key it read at
its place (``placed``), so an answer keeps that key there, as a read keeps a list's item. It
hands out its own copy of each key, so a lookup of that very object, whenever it runs, is one no
input fails and records no fork (``proven``); a key Python shares with the target's literals has
no copy, and its lookup records the place the walk read it first (``handout``).

`len(config)` and `bool(config)` where pyct binds or routes them, and on each of its views, read
the size term, `["len", config]` and what the target added or removed, and record no fork where
they run. A walk's pass or end, and a truth test, that the dict's range proves
(``DictState.measured``) is a fact, not a fork.
"""

from __future__ import annotations

import json
import numbers
from collections.abc import Callable, Iterator
from typing import Any

from pyct.core.bools import ConcolicBool
from pyct.core.branch import Branch, Downgrade, Expression, Fact, caller_site
from pyct.core.dict_compares import (
    after_changes,
    handed_in_place,
    is_tracked,
    own_key,
    written_key,
)
from pyct.core.dict_handouts import (
    FIRST,
    LAST,
    POPPED,
    given_place,
    handout,
    proven,
    stale_copy,
    walked_in_the_argument,
)
from pyct.core.dict_state import MISSING, TRACKED, DictState
from pyct.core.ints import ConcolicInt
from pyct.core.list_reads import caller
from pyct.core.list_state import plain
from pyct.core.spans import decided, narrowed, proves
from pyct.core.strs import ConcolicStr
from pyct.core.values import forked, own

# what a walk hands out for each key: the key, its value, or both
type Pick = Callable[[DictState, object], object]


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


def settled_as(key: object) -> object:
    """What ``settled`` knows a key by: a plain key as itself, a tracked one by its expression."""
    if is_tracked(key):
        assert isinstance(key, ConcolicStr | ConcolicInt)
        return ("tracked", json.dumps(key.expression))
    return key


def present(
    self: DictState, key: object, name: str, *, raising: bool = False, changing: bool = False
) -> bool | None:
    """Whether the dict holds ``key``, recording the fork the first time the path asks, which
    settles the answer: a later lookup of the same key, with no change under it since, is a
    fact that holds what the first found, and so is a lookup in a dict whose range holds no
    key (``DictState.measured``). On a dict changed without a fork no lookup is a
    fact, since that change may have touched the key on another input: one recorded here is a
    fork, and a key the target changed or a walk handed out is answered without either. After
    a change under a tracked key the lookup first records whether its key is that one
    (``after_changes``), until a walk follows such a change: from then on no key is compared
    with a tracked change (``DictState.unfollowed_since_walk``).

    A key Python shares with the target's literals that a walk handed out keeps the place the
    walk read it, given by the lookup: a fact recorded before the fork, which holds on both its
    sides.

    None when pyct does not follow this lookup, which the caller answers as Python does and
    names as a downgrade: a key of another kind, or a tracked key into a dict the target
    changed, unless the lookup is a change's own (``changing``). Python's own lookup compares a
    key it finds with `==`, which on a tracked key records a fork no target wrote, so every
    lookup here reads the key's plain value.
    """
    held = dict.__contains__(self, plain(key))
    if proven(self, key):
        return held
    if self.unfollowed_since_walk():
        self.changed_unforked()
        return _looked_up_unfollowed(self, key, held, (name, raising))
    written = written_key(key)
    if written is None or (is_tracked(key) and self.changed and not changing):
        return None
    given = given_place(self, key)
    place: Expression = None if given is None else ["given", given]
    # whether the key is one a change was made under holds where the walk read it, too
    changed = after_changes(self, key, written, (name, raising, place))
    if changed is not None:
        return changed
    return _in_the_argument(self, key, held, (name, raising, place))


def _looked_up_unfollowed(
    self: DictState, key: object, held: bool, how: tuple[str, bool]
) -> bool | None:
    """A lookup in a dict no longer followed (see ``DictState.unfollowed_since_walk``): no key
    is compared with a tracked change. None for a key of another kind and a tracked key, which
    the caller answers as Python does, the dict holding a change; no fork for a key the target
    changed or a walk handed out, a stale copy among them; and otherwise the argument's fork on
    the marked dict, given where a walk read a key Python shares."""
    name, raising = how
    if written_key(key) is None or is_tracked(key):
        return None
    if plain(key) in self.changed or stale_copy(self, key):
        return held
    given = self.shared.get(key)
    place: Expression = None if given is None else ["given", given]
    return _in_the_argument(self, key, held, (name, raising, place))


def _in_the_argument(
    self: DictState, key: object, held: bool, how: tuple[str, bool, Expression]
) -> bool:
    """Whether the argument holds ``key``, a key no change decides: the fork, or a fact where
    the path asked before (see ``present``) or a walk read the key in the argument. ``how`` is
    the lookup's name, whether Python may raise after it, and the place a walk read the key at,
    which holds on both sides."""
    name, raising, place = how
    known = settled_as(key)
    test = ["in", written_key(key), self.expression]
    site = caller_site()
    self.settled.setdefault(known, held)
    # after a change without a fork, a lookup recorded here is a fork, and adds nothing to the
    # keys asked and found that the argument's other dicts decide by; ``settled``, shared too,
    # is still noted
    if not self.unforked:
        # a key the path asked about before, a stale copy of a key a walk read in the
        # argument, or any key of a dict whose range holds none
        decided = (
            known in self.asked
            or (held and walked_in_the_argument(self, key))
            or (self.measured()[1] == 0 and not held)
        )
        self.asked.add(known)
        if held:
            self.found.add(TRACKED if is_tracked(key) else known)
        if decided:
            self.sink.append(Fact(test, held, site, raising, place, lost_as=name))
            return held
    if place is not None:
        self.sink.append(Fact(None, True, site, raising, place, lost_as=name))
    return recorded(self, Branch(test, held, site, raising, name))


def recorded(self: DictState, branch: Branch) -> bool:
    """Record a fork, and answer with the side it took."""
    self.sink.append(branch)
    return branch.taken


def found(
    self: DictState, key: object, name: str, *, raising: bool = False, changing: bool = False
) -> bool:
    """Whether the dict holds ``key``, answered and recorded where pyct follows the lookup, and
    otherwise Python's answer, named ``name``: a key of another kind is Python's to hash.
    ``changing`` says the lookup is a change's own (see ``present``)."""
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
    answer = present(self, looked, name, raising=raising, changing=changing)
    if answer is None:
        self.sink.append(Downgrade(name=name, site=caller_site()))
        if is_tracked(looked):
            # Python answered for this key's value with no fork, so a fork on the key after it
            # would move an answer the path already read (see ``dict_changes.followed``)
            self.unfollowed.add(settled_as(looked))
        return dict.__contains__(self, bare)
    return answer


def value(self: DictState, key: object, *, changing: bool = False) -> object:
    """The value under a key the dict holds, handed out as the target reads it.

    A tracked key reads the argument's value as ``config[name]``, so the solver may change the
    key; any other key hands out what the dict holds there. So does a tracked key into a dict
    the target changed, unless a change's own lookup (``changing``) found the key none of the
    changed ones, and so the argument's.
    """
    held = dict.__getitem__(self, plain(key))
    if not is_tracked(key) or self.expression is None:
        return held
    if self.changed and not (changing and plain(key) not in self.changed):
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
    term its own forks read, and its range as it is now (see ``ConcolicInt.span``). A dict
    with no form gives its plain size."""
    if not self.holds("__len__"):
        return self.size()
    measured = ConcolicInt.made(self.size(), self.size_term(), self.sink)
    measured.__dict__["span"] = self.measured()
    return measured


def truth(self: DictState) -> bool:
    """``if config:``: Python tests a dict by its size, so the check is `len(config) != 0`: a
    fact where the dict's range proves it (``DictState.measured``), else a fork, which narrows
    the range."""
    filled = self.size() != 0
    if not self.holds("__bool__"):
        return filled
    test: list[Expression] = ["!=", self.size_term(), 0]
    if decided(self.sink, self.measured(), test, filled):
        return filled
    self.__dict__["span"] = narrowed(self.span, "!=", 0, filled)
    return forked(self.sink, test, filled)


def condition(self: DictState) -> Any:
    """`bool(config)` where pyct routes `bool`: the condition `if config:` tests, as a tracked
    bool that records no fork, so the fork is recorded where the target tests it.

    It holds the dict's size term at the call, which a later change replaces rather than edits.
    A dict with no form gives Python's plain answer; one whose form stopped describing it does
    too, naming `__bool__` as `if config:` does. Where the dict's range proves the answer, the
    fact is recorded where `bool` is called, and the answer is a plain bool.
    """
    filled = self.size() != 0
    if not self.holds("__bool__"):
        return filled
    test: list[Expression] = ["!=", self.size_term(), 0]
    if decided(self.sink, self.measured(), test, filled):
        return filled
    return ConcolicBool.made(filled, test, self.sink)


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
    if own_key(self, key):
        return None if end in (LAST, POPPED) else ["exactly", self.expression]
    return [end if end in (LAST, POPPED) else "walked", self.expression, written]


def _walked(
    self: DictState, keys: Iterator[object], pick: Pick, how: tuple[str, str]
) -> Iterator[object]:
    """Each key in Python's own order: Python's own iterator raises where the dict changes size
    while it walks. A change made without the dict's methods turns the walk plain there. Each
    key is handed out as the walk's own copy of it (see ``handout``)."""
    name, end = how
    first = self.walk_started()
    at = 0
    while True:
        key = own(next, keys, MISSING)
        if not self.holds(name, *(() if key is MISSING else (key,))):
            break
        pin = None if key is MISSING else placed(self, key, end)
        if not passed(self, at, key, pin, name):
            return
        if first or not self.unfollowed_since_walk():
            handed_in_place(self, key, name, pin)
        handout(self, key, pin)
        yield pick(self, key)
        at += 1
    while key is not MISSING:
        yield plain_pick(pick, self, key)
        key = own(next, keys, MISSING)


def passed(self: DictState, at: int, key: object, pin: Expression, name: str) -> bool:
    """Record whether a walk takes pass ``at``, and answer it: a fact where the dict's range
    proves the answer (``DictState.measured``), a pass with the place it read its key at, else
    a fork, which narrows the range; then the place the pass read its key at, a fact that
    holds only on the side the pass took."""
    test = [">", self.size_term(), at]
    site = caller_site()
    taken = key is not MISSING
    if proves(self.measured(), ">", at) is taken:
        self.sink.append(Fact(test, taken, site, False, pin if taken else None, lost_as=name))
        return taken
    self.__dict__["span"] = narrowed(self.span, ">", at, taken)
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

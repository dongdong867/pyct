"""Whether a key is one a change under a tracked key made: the compares a lookup, a walk or
popitem records after such a change (dict-keys-named-held-made-up-or-changed-under-a-tracked-key).

A plain key and a plain change decide by their values. Where either is tracked, the solver may
make the two keys equal or not, so the lookup records whether they are, `["==", "n", "'b'"]`,
once for each pair the path compares. A walk that hands out one of the argument's keys compares
it only with the tracked stores that may be over it.
"""

from __future__ import annotations

import json

from pyct.core.branch import Branch, Expression, Fact, caller_site
from pyct.core.dict_state import Change, DictState
from pyct.core.ints import ConcolicInt
from pyct.core.list_state import plain
from pyct.core.strs import ConcolicStr


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


def is_tracked(key: object) -> bool:
    """Whether a key is a tracked str or int, which the solver may change."""
    return type(key) is ConcolicStr or type(key) is ConcolicInt


def after_changes(
    self: DictState,
    key: object,
    written: Expression,
    how: tuple[str, bool, Expression],
    *,
    handed: bool = False,
) -> bool | None:
    """Whether the dict holds ``key`` by a change the target made, the latest first, or None
    when no change decides it and the argument's own keys do.

    A plain key and a plain change decide by their values. Where either is tracked, the
    solver may make the two keys equal or apart, so the lookup records whether they are,
    `["==", "n", "'b'"]`, the side Python took, at the lookup's own site; a key equal to the
    change's decides. Keys of different kinds never are equal, and one expression always is.
    ``how`` is the lookup's name, whether Python may raise after it, and the place each fork it
    records keeps, a fact recorded before it (see ``Fact.place``). A key a walk ``handed`` out
    is compared only with the tracked stores that may be over it (see ``over_the_argument``).
    """
    bare = plain(key)
    tracked = is_tracked(key)
    if not tracked and not self.tracked_changes:
        return self.changed.get(bare)
    unequal: list[Expression] = []
    for change in _after_the_last_plain(self, bare) if not tracked else reversed(self.log):
        under, changed, stored, _ = change
        if type(changed) is not type(bare):
            continue
        if under is None and not tracked:
            if changed == bare:
                return stored
            continue
        if handed and not over_the_argument(self, change):
            continue
        other = written_key(changed) if under is None else under
        if other == written:
            return stored
        if other not in unequal:
            pair = [written, other] if tracked else [other, written]
            if _compared(self, pair, changed == bare, how):
                return stored
            unequal.append(other)
    return None


def _after_the_last_plain(self: DictState, bare: object) -> list[Change]:
    """The changes a plain key's lookup reads, the latest first: each change under a tracked key
    after the key's own latest change under a plain key, and then that one, which decides."""
    last = self.plain_at.get(bare, -1)
    if last >= 0 and type(self.log[last][1]) is not type(bare):
        last = -1
    after = [self.log[at] for at in reversed(self.tracked_at) if at > last]
    return after + ([self.log[last]] if last >= 0 else [])


def _compared(
    self: DictState, pair: list[Expression], equal: bool, how: tuple[str, bool, Expression]
) -> bool:
    """Record whether two keys are equal, the tracked one first, and answer whether they are.

    A pair the path already compared records nothing more, and neither does a tracked key the
    path already found equal to a literal, compared with another literal: the path decides
    both, so no input takes their other side.
    """
    tracked, other = (json.dumps(part) for part in pair)
    pinned = self.compared.get((tracked, "=="))
    if (tracked, other) in self.compared or (pinned is not None and _literal(pair[1])):
        return equal
    name, raising, place = how
    self.compared[(tracked, other)] = equal
    if equal and _literal(pair[1]):
        self.compared[(tracked, "==")] = True
    site = caller_site()
    if place is not None:
        # the place holds on both sides of the fork, so it is a fact recorded before it
        self.sink.append(Fact(None, True, site, raising, place, lost_as=name))
    self.sink.append(Branch(["==", *pair], equal, site, raising, name))
    return equal


def _literal(written: Expression) -> bool:
    """Whether a key as a fork writes it is a literal: an int, or a str in its quotes."""
    return type(written) is int or (type(written) is str and written[:1] in ("'", '"'))


def over_the_argument(self: DictState, change: Change) -> bool:
    """Whether a change is a store under a tracked key that may be over one of the argument's
    keys in its place: the dict held the key, and the path did not settle that the argument
    lacks it. A walk that hands out an argument's key compares it only with these. A removal
    under a tracked key, and a store that puts its key last again, stay Python's own there,
    since an answer that moves either to another key walks another key in its place."""
    under, changed, stored, held = change
    return under is not None and stored and held and self.settled.get(changed) is not False


def own_key(self: DictState, key: object) -> bool:
    """Whether the dict holds a key of the target's own: one it stored that the argument did
    not hold."""
    return self.changed.get(key) is True and self.settled.get(key) is False


def compared_in_place(self: DictState, key: object) -> bool:
    """Whether a key of the argument a walk or popitem hands out may be one a tracked key
    stored over (see ``over_the_argument``). The target's own key is wherever its store put
    it."""
    if not self.tracked_changes or written_key(key) is None or own_key(self, key):
        return False
    return any(
        type(change[1]) is type(key) and over_the_argument(self, change) for change in self.log
    )


def handed_in_place(self: DictState, key: object, name: str, pin: Expression) -> None:
    """Record, for a key of the argument a walk or popitem hands out, whether each tracked key
    that may have changed it did, so an answer keeps the value there (``compared_in_place``).
    Each such fork keeps the key where the walk read it (``pin``) whatever a fork reads, a
    given place recorded before it, so the key it compares is the one an answer's walk reads
    there; the walk's own place holds only on the side its pass took, so its flip may still
    end the walk sooner."""
    if compared_in_place(self, key):
        place: Expression = None if pin is None else ["given", pin]
        after_changes(self, key, written_key(key), (name, False, place), handed=True)

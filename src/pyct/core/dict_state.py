"""What a tracked dict keeps beside its items: the argument it came from, what the path settled
about that argument's keys, and what the target changed since.

A tracked dict is a real dict, so C code reads its items where they are. A dict the target
changed is never written whole (follow-lists-and-dicts-as-they-change): its form is the access
of the argument it came from, and beside it the dict keeps which keys the path has asked about
and found there or not (``settled``, shared by every dict made from that argument), and which
keys the target stored or removed since (``changed``), each change in order in ``log``. So after
each change a key's presence is known, a value is its own expression, and the size is the
argument's size plus what changed.

A shadow keeps the items as pyct last saw them. Code that changes the dict without its methods,
``dict.__setitem__(config, k, v)`` say, leaves the shadow behind, and the next operation that
reads the size or a key sees it.
"""

from __future__ import annotations

from typing import Self

from pyct.core.branch import BranchSink, Downgrade, Expression, caller_site
from pyct.core.list_state import plain

# what a key maps to where the dict holds no such key: apart from every value a dict holds
MISSING = object()

# one change the target made: the expression of the tracked key it was made under, None under a
# plain key; the key's plain value; whether the change stored the key (True) or removed it; and
# whether a store kept the key in the argument's place: the dict held it when it ran, and no
# change before it took the key out or put it in anew (see ``DictState.never_moved``)
type Change = tuple[Expression, object, bool, bool]

# what ``found`` holds for any tracked key a fork found, which may equal any other key
TRACKED = object()


class DictState(dict):
    """The state a tracked dict keeps beside its items, and what every operation checks first.

    ``expression`` is the access of the argument the dict came from, None once the dict is
    plain: a change made without its methods left the form behind for good, or the target
    emptied it. ``settled`` holds, by each key the path asked about, whether the argument held
    it; ``changed`` whether the dict holds each key the target stored (True) or removed (False).
    The dict refuses a set, as a plain one does, so pyct writes these fields straight into its
    ``__dict__``.
    """

    expression: Expression | None
    sink: BranchSink
    settled: dict[object, bool]
    changed: dict[object, bool]
    # each pair of keys a fork compared, a tracked one first, each written as JSON, and whether
    # they were equal; and each tracked key found equal to a literal, paired with "=="
    compared: dict[tuple[str, str], bool]
    # every change in the order the target made it, and how many were under a tracked key,
    # which a later lookup compares its own key with (see ``dict_compares.after_changes``)
    log: list[Change]
    tracked_changes: int
    # where in ``log`` each plain key's latest change under a plain key sits, and where each
    # change under a tracked key does, so a plain key's lookup reads only the changes after it
    plain_at: dict[object, int]
    tracked_at: list[int]
    # how many keys the dict holds past the argument's own: each change's, kept as it happens
    grown: int
    # each key a fork of the path asked about, as ``settled`` knows it, and those it found in
    # the argument, a tracked key as ``TRACKED`` (see ``fewest``), both shared as ``settled`` is.
    # Kept apart from ``settled``, which also notes a key a change pyct does not follow met,
    # with no fork
    asked: set[object]
    found: set[object]
    # whether the target changed the dict in a way pyct answered without a fork, as a store
    # under a tracked float key: that change may touch any key on another input, so after it no
    # lookup is decided, and the fewest keys are only ``floor``, which each change since
    # moves as it would move whichever key it touched (see ``fewest``)
    unforked: bool
    floor: int
    shadow: dict[object, object]
    # the caller's frame and instruction when a walk last started, so Python's own guess at the
    # size that follows it in the same call is not taken for the target's `len`
    walked_at: tuple[int, int] | None
    # the copy of each stored key every walk hands out, so a lookup of that very object comes
    # from a walk; and, for a key Python shares, which no copy can stand for, where a walk read
    # it (see ``dict_handouts.proven``)
    copies: dict[object, object]
    shared: dict[object, Expression]
    # each copy a walk handed out, by its identity: the copy, and where the walk last read its
    # key; and the copies a change under a tracked key may have touched, which a lookup no
    # longer takes as proven and asks again, given that place (see ``dict_handouts``)
    handed: dict[int, tuple[object, Expression]]
    stale: set[int]
    # whether popitem changed the dict: it removes whichever key is last on the input, so a
    # change under a tracked key after it is Python's own (see ``dict_changes.followed``)
    popped: bool
    # each tracked key a lookup answered as Python's own, with no fork, as ``settled`` knows it:
    # a change under it after that is Python's own too (see ``dict_changes.followed``)
    unfollowed: set[object]
    # whether a walk of this dict, or of one made from the same argument, ran after a change
    # under a tracked key: one list shared by reference, so a copy's walk counts too. From
    # then on a dict of them changed under a tracked key is not followed (see
    # ``unfollowed_since_walk``)
    walked_after: list[bool]
    # whether the argument's annotation is `dict[int, X]`, to which the solver adds int keys,
    # named or made up: a key pyct does not follow that may equal an int turns such a dict
    # plain (see ``dict_reads.may_equal_added``)
    int_keyed: bool

    @classmethod
    def made(
        cls,
        items: dict[object, object],
        expression: Expression | None,
        sink: BranchSink,
        *,
        int_keyed: bool = False,
    ) -> Self:
        """A tracked dict of these items and this argument, nothing settled or changed yet."""
        # dict's own, since the class called with a value builds a plain dict
        made = dict.__new__(cls)
        dict.update(made, items)
        fields = made.__dict__
        fields["expression"] = expression
        fields["sink"] = sink
        fields["settled"] = {}
        fields["asked"] = set()
        fields["found"] = set()
        fields["unforked"] = False
        fields["floor"] = 0
        fields["changed"] = {}
        # the changes, none yet (see ``logged``)
        fields.update(compared={}, log=[], plain_at={}, tracked_at=[], tracked_changes=0)
        fields["grown"] = 0
        fields["shadow"] = dict(items)
        fields["walked_at"] = None
        # what walks handed out, none yet (see ``dict_handouts.handout``)
        fields.update(
            copies={},
            shared={},
            handed={},
            stale=set(),
            popped=False,
            unfollowed=set(),
            walked_after=[False],
        )
        fields["int_keyed"] = int_keyed
        return made

    def size(self) -> int:
        """The number of keys, as C code reads it: not `len`, which records `__len__`."""
        return dict.__len__(self)

    def storage(self) -> dict[object, object]:
        """The items as a plain dict, read in C without walking them: `dict.copy` of a dict whose
        `keys` is its own would ask `keys`, and walk it."""
        return dict(dict.items(self))

    def size_term(self) -> Expression:
        """The size as a fork writes it: the argument's size, plus the keys the target added
        and less the keys it removed."""
        measured: Expression = ["len", self.expression]
        grown = self.grown
        if grown == 0:
            return measured
        return ["+", measured, grown] if grown > 0 else ["-", measured, -grown]

    def fewest(self) -> int:
        """The fewest keys the dict holds on every input that takes the path so far: the keys a
        fork of the path found in the argument, plus the keys the target added less those it
        removed.

        A tracked key found counts only where no plain key was found, since it may equal any
        of them. A key found is the argument's, whatever the target did since: a removal of it
        is counted in ``grown``. That count is what the size term, `len` of the argument plus
        ``grown``, reaches on every input the forks allow, so a check it decides holds as
        written.

        A dict changed without a fork (``unforked``) set ``grown`` from this input's own keys,
        so the dict may hold fewer on another input. It holds at least ``floor``, counted from
        what it knew before that change: a store keeps every key and leaves one, whichever it
        is, and a removal may take any one. A check is decided only where both counts reach it.
        """
        found = self.found
        plain_found = len(found) - (TRACKED in found)
        written = max(plain_found, 1 if found else 0) + self.grown
        return min(written, self.floor) if self.unforked else written

    def current(self, *keys: object) -> bool:
        """Whether the form still describes the dict: its size and each key read.

        One whose items were changed without its methods turns plain here, so no fork reads a
        form that no longer matches. ``holds`` asks it only of a dict that has a form.
        """
        matches = self.size() == len(self.shadow) and all(
            dict.get(self, key, MISSING) is self.shadow.get(key, MISSING) for key in keys
        )
        if not matches:
            self.turn_plain()
        return matches

    def holds(self, name: str, *keys: object) -> bool:
        """Whether the form still describes the dict, naming ``name`` when it just stopped.

        A dict already plain records nothing: a plain dict's operations are Python's own.
        """
        if self.expression is None:
            return False
        if self.current(*keys):
            return True
        self.sink.append(Downgrade(name=name, site=caller_site()))
        return False

    def lose(self, name: str) -> None:
        """The dict turns plain, and the line names the operation that lost it."""
        self.turn_plain()
        self.sink.append(Downgrade(name=name, site=caller_site()))

    def turn_plain(self) -> None:
        """Drop the form, and with it the conditions of the values the argument put here.

        Each tracked int, str and bool is its value from now on; a list or a dict inside,
        tracked in its own right, stays where it is.
        """
        self.__dict__["expression"] = None
        for key, value in dict.items(self.storage()):
            dict.__setitem__(self, key, plain(value))

    def derived(self, items: dict[object, object]) -> DictState:
        """A new tracked dict of the same argument: these items, and what this one settled and
        changed, the argument's settled keys shared."""
        made = type(self).made(items, self.expression, self.sink, int_keyed=self.int_keyed)
        fields = made.__dict__
        fields["settled"] = self.settled
        fields["compared"] = self.compared
        fields["asked"] = self.asked
        fields["found"] = self.found
        fields["unforked"] = self.unforked
        fields["floor"] = self.floor
        fields["changed"] = dict(self.changed)
        fields["log"] = list(self.log)
        fields["plain_at"] = dict(self.plain_at)
        fields["tracked_at"] = list(self.tracked_at)
        fields["tracked_changes"] = self.tracked_changes
        fields["grown"] = self.grown
        fields["popped"] = self.popped
        fields["unfollowed"] = set(self.unfollowed)
        fields["walked_after"] = self.walked_after
        return made

    def noted(self, key: object, value: object, tracked: Expression = None) -> None:
        """Note a change the dict's own method made: the key now holds ``value``. The shadow
        still says whether it held the key before, which is how the size grew. ``tracked`` is
        the expression of the tracked key the change was made under."""
        held = key in self.shadow
        self.__dict__["grown"] += not held
        self.shadow[key] = value
        self.logged(key, (True, held), tracked)
        self.held_one()

    def unfollowed_since_walk(self) -> bool:
        """Whether this dict was changed under a tracked key and a walk of it, or of a dict made
        from the same argument, ran after such a change: then its lookups, changes and later
        walks are not followed (see ``dict_reads.present``). A walk hands out the tracked key's
        own key, and a key Python shares is the very object a literal is, so no later lookup
        tells the two apart, and comparing them pins the tracked key. A caller that acts on it
        marks the dict (``changed_unforked``)."""
        return self.walked_after[0] and self.tracked_changes > 0

    def walk_started(self) -> bool:
        """Note a walk of the dict, and answer whether it is the first since a change under a
        tracked key: that walk compares what it hands out as before (``handed_in_place``), and
        the dict is marked; from then on it is not followed (``unfollowed_since_walk``)."""
        if not self.tracked_changes or self.walked_after[0]:
            return False
        self.walked_after[0] = True
        self.changed_unforked()
        return True

    def changed_unforked(self) -> None:
        """Note a change pyct answered without a fork: from now on no lookup is decided, and
        the fewest keys count from what the dict knew before it."""
        if not self.unforked:
            self.__dict__["floor"] = self.fewest()
            self.__dict__["unforked"] = True

    def held_one(self) -> None:
        """Note that a change left a key in the dict, whichever key it is on another input."""
        self.__dict__["floor"] = max(self.floor, 1)

    def lost_one(self) -> None:
        """Note that a change may have removed one key on another input that takes the path."""
        self.__dict__["floor"] = max(self.floor - 1, 0)

    def dropped(self, key: object, tracked: Expression = None) -> None:
        """Note a removal the dict's own method made."""
        self.__dict__["grown"] -= key in self.shadow
        self.shadow.pop(key, None)
        self.logged(key, (False, True), tracked)
        self.lost_one()

    def never_moved(self, key: object, tracked: Expression) -> bool:
        """Whether no change before this one took ``key`` out or put it in anew, under the same
        tracked key or as the same plain key: then a store over it keeps the argument's place,
        and otherwise its key is last, where a removal and a store put it again."""
        return not any(
            (under == tracked or (type(changed) is type(key) and changed == key))
            and not (stored and held)
            for under, changed, stored, held in self.log
        )

    def logged(self, key: object, how: tuple[bool, bool], tracked: Expression = None) -> None:
        """Log a change: whether it stored the key or removed it, and whether the dict held the
        key when it ran (``how``).

        A change under a tracked key that may touch a key the dict holds, a removal or a store
        over a held key, makes the walks' copies stale: the solver may make that key a copied
        one, which a removal takes out and a store gives another value, so a lookup of a copy
        handed out before it asks again, given where the walk read it. A store of a key the dict
        did not hold is apart, by its forks, from every key a walk handed out.
        """
        stored, held = how
        self.changed[key] = stored
        at = len(self.log)
        in_place = held and (tracked is None or self.never_moved(key, tracked))
        self.log.append((tracked, key, stored, in_place))
        if tracked is None:
            self.plain_at[key] = at
        else:
            self.tracked_at.append(at)
            self.__dict__["tracked_changes"] += 1
            if held or not stored:
                self.stale.update(id(copied) for copied in self.copies.values())
                self.copies.clear()

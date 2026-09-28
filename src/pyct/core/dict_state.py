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
# plain key; the key's plain value; and whether the change stored the key (True) or removed it
type Change = tuple[Expression, object, bool]


def _tracked_key(key: object) -> bool:
    """Whether a settled key is a tracked key's, which ``dict_reads.settled_as`` writes as a
    pair."""
    return isinstance(key, tuple) and key[:1] == ("tracked",)


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
    # each key a recorded fork found the argument holds, as ``settled`` knows it, shared as it is
    found_held: set[object]
    # each pair of keys a fork compared, a tracked one first, each written as JSON, and whether
    # they were equal; and each tracked key found equal to a literal, paired with "=="
    compared: dict[tuple[str, str], bool]
    # every change in the order the target made it, and how many were under a tracked key,
    # which a later lookup compares its own key with (see ``dict_reads.after_changes``)
    log: list[Change]
    tracked_changes: int
    # how many keys the dict holds past the argument's own: each change's, kept as it happens
    grown: int
    shadow: dict[object, object]
    # the caller's frame and instruction when a walk last started, so Python's own guess at the
    # size that follows it in the same call is not taken for the target's `len`
    walked_at: tuple[int, int] | None
    # the copy of each stored key every walk hands out, so a lookup of that very object comes
    # from a walk; and, for a key Python shares, which no copy can stand for, where a walk read
    # it (see ``dict_reads.proven``)
    copies: dict[object, object]
    shared: dict[object, Expression]
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
        fields["changed"] = {}
        fields["found_held"] = set()
        fields["compared"] = {}
        fields["log"] = []
        fields["tracked_changes"] = 0
        fields["grown"] = 0
        fields["shadow"] = dict(items)
        fields["walked_at"] = None
        fields["copies"] = {}
        fields["shared"] = {}
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

    def least_size(self) -> int:
        """The fewest keys the dict holds on any input that takes the path so far: the keys the
        path found the argument holds, at least one where a tracked key was among them, plus
        the keys the target added and less the keys it removed."""
        found = self.found_held
        named = sum(1 for key in found if not _tracked_key(key))
        return max(named, 1 if found else 0) + self.grown

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
        fields["found_held"] = self.found_held
        fields["compared"] = self.compared
        fields["changed"] = dict(self.changed)
        fields["log"] = list(self.log)
        fields["tracked_changes"] = self.tracked_changes
        fields["grown"] = self.grown
        return made

    def noted(self, key: object, value: object, tracked: Expression = None) -> None:
        """Note a change the dict's own method made: the key now holds ``value``. The shadow
        still says whether it held the key before, which is how the size grew. ``tracked`` is
        the expression of the tracked key the change was made under."""
        self.__dict__["grown"] += key not in self.shadow
        self.shadow[key] = value
        self.logged(key, True, tracked)

    def dropped(self, key: object, tracked: Expression = None) -> None:
        """Note a removal the dict's own method made."""
        self.__dict__["grown"] -= key in self.shadow
        self.shadow.pop(key, None)
        self.logged(key, False, tracked)

    def logged(self, key: object, stored: bool, tracked: Expression = None) -> None:
        """Log a change, whether it stored the key or removed it.

        A change under a tracked key drops the walks' copies: the solver may make that key a
        copied one, which a removal takes out and a store gives another value, so a lookup of
        a copy handed out before it asks again.
        """
        self.changed[key] = stored
        self.log.append((tracked, key, stored))
        if tracked is not None:
            self.__dict__["tracked_changes"] += 1
            self.copies.clear()

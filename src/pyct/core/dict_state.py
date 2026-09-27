"""What a tracked dict keeps beside its items: the argument it came from, what the path settled
about that argument's keys, and what the target changed since.

A tracked dict is a real dict, so C code reads its items where they are. A dict the target
changed is never written whole (follow-lists-and-dicts-as-they-change): its form is the access
of the argument it came from, and beside it the dict keeps which keys the path has asked about
and found there or not (``settled``, shared by every dict made from that argument), and which
keys the target stored or removed since (``changed``). So after each change a key's presence is
known, a value is its own expression, and the size is the argument's size plus what changed.

A shadow keeps the items as pyct last saw them. Code that changes the dict without its methods,
``dict.__setitem__(config, k, v)`` say, leaves the shadow behind, and the next operation that
reads the size or a key sees it.
"""

from __future__ import annotations

from typing import Self

from pyct.core.branch import BranchSink, Downgrade, Expression
from pyct.core.list_state import plain

# what a key maps to where the dict holds no such key: apart from every value a dict holds
MISSING = object()


class DictState(dict):
    """The state a tracked dict keeps beside its items, and what every operation checks first.

    ``expression`` is the access of the argument the dict came from, None once the dict is
    plain: a change made without its methods left the form behind for good, or the target
    emptied it. ``settled`` holds, by each key the path asked about, whether the argument held
    it; ``changed`` whether the dict holds each key the target stored (True) or removed (False).
    """

    expression: Expression | None
    sink: BranchSink
    settled: dict[object, bool]
    changed: dict[object, bool]
    # how many keys the dict holds past the argument's own: each change's, kept as it happens
    grown: int
    shadow: dict[object, object]
    # the caller's frame and instruction when a walk last started, so Python's own guess at the
    # size that follows it in the same call is not taken for the target's `len`
    walked_at: tuple[int, int] | None

    @classmethod
    def made(
        cls, items: dict[object, object], expression: Expression | None, sink: BranchSink
    ) -> Self:
        """A tracked dict of these items and this argument, nothing settled or changed yet."""
        made = cls.__new__(cls)
        dict.update(made, items)
        made.expression = expression
        made.sink = sink
        made.settled = {}
        made.changed = {}
        made.grown = 0
        made.shadow = dict(items)
        made.walked_at = None
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
        self.sink.append(Downgrade(name=name))
        return False

    def lose(self, name: str) -> None:
        """The dict turns plain, and the line names the operation that lost it."""
        self.turn_plain()
        self.sink.append(Downgrade(name=name))

    def turn_plain(self) -> None:
        """Drop the form, and with it the conditions of the values the argument put here.

        Each tracked int, str and bool is its value from now on; a list or a dict inside,
        tracked in its own right, stays where it is.
        """
        self.expression = None
        for key, value in dict.items(self.storage()):
            dict.__setitem__(self, key, plain(value))

    def derived(self, items: dict[object, object]) -> DictState:
        """A new tracked dict of the same argument: these items, and what this one settled and
        changed, the argument's settled keys shared."""
        made = type(self).made(items, self.expression, self.sink)
        made.settled = self.settled
        made.changed = dict(self.changed)
        made.grown = self.grown
        return made

    def noted(self, key: object, value: object) -> None:
        """Note a change the dict's own method made: the key now holds ``value``. The shadow
        still says whether it held the key before, which is how the size grew."""
        self.grown += key not in self.shadow
        self.shadow[key] = value
        self.changed[key] = True

    def dropped(self, key: object) -> None:
        """Note a removal the dict's own method made."""
        self.grown -= key in self.shadow
        self.shadow.pop(key, None)
        self.changed[key] = False

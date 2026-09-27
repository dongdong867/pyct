"""What a tracked list keeps beside its items: its form, its sink, and what pyct last saw.

A tracked list is a real list, so C code reads its items where they are. Beside them it keeps
the Python expression that builds it from the arguments (a-changed-list-prints-as-python-builds-it),
the kinds of the items that form can hand out, and a shadow: the items as pyct last saw them, one
per position. Code that changes the list without its methods, `heapq.heappush` say, leaves the
shadow behind, and the next operation that reads a position or the length sees it.
"""

from __future__ import annotations

from collections.abc import Iterable

from pyct.core.bools import ConcolicBool
from pyct.core.branch import BranchSink, Downgrade, Expression
from pyct.core.ints import ConcolicInt
from pyct.core.strs import ConcolicStr

# the kinds of item a read hands out as a tracked value: each has a concolic type of its own
TRACKED = frozenset({"int", "str"})

# the kind each type of item is, by exact type: a subclass the target wrote is its own kind
_KINDS: dict[type, str] = {
    int: "int",
    ConcolicInt: "int",
    str: "str",
    ConcolicStr: "str",
    bool: "bool",
    ConcolicBool: "bool",
    float: "float",
    type(None): "none",
    list: "list",
    dict: "dict",
}


def kind_of(item: object) -> str:
    """The kind of one item: what the solver keeps for it at its position."""
    kind = _KINDS.get(type(item))
    if kind is not None:
        return kind
    return "list" if isinstance(item, ListState) else "other"


def kinds_of(items: Iterable[object]) -> frozenset[str]:
    """The kinds of every item, as a set."""
    return frozenset(map(kind_of, items))


def is_static(expression: Expression) -> bool:
    """Whether a list's form names an argument's list as it came: a parameter, or an access.

    Such a list is the one the input holds, so the kind at each position of it is the input's,
    and a read at a position from the start is typed by that position alone.
    """
    step = expression
    while isinstance(step, list):
        if len(step) != 3 or step[0] != "[]" or isinstance(step[2], list):
            return False
        step = step[1]
    return isinstance(step, str) and not step.startswith(("'", '"'))


class ListState(list):
    """The state a tracked list keeps beside its items, and what every operation checks first.

    ``expression`` is None once the list is plain: a change pyct could not write, or one made
    without the list's methods, left the form behind for good.
    """

    expression: Expression | None
    sink: BranchSink
    shadow: list[object]
    kinds: frozenset[str]
    # the caller's frame and instruction when a walk last started, so Python's own guess at the
    # length that follows it in the same call is not taken for the target's `len`
    walked_at: tuple[int, int] | None

    @classmethod
    def made(
        cls, items: list[object], expression: Expression | None, sink: BranchSink
    ) -> ListState:
        """A tracked list of these items and this form, its shadow the items themselves."""
        made = cls.__new__(cls)
        list.extend(made, items)
        made.sink = sink
        made.shadow = list(items)
        made.expression = expression
        made.kinds = kinds_of(items)
        made.walked_at = None
        return made

    def length(self) -> int:
        """The number of items, as C code reads it: not `len`, which records `__len__`."""
        return list.__len__(self)

    def storage(self) -> list[object]:
        """The items as a plain list, read in C without walking them."""
        return list.copy(self)

    def current(self, *positions: int) -> bool:
        """Whether the form still describes the list: its length and each position read.

        A list already plain has no form to describe it. One whose items were changed without
        its methods turns plain here, so no fork reads a form that no longer matches.
        """
        if self.expression is None:
            return False
        size = self.length()
        matches = size == len(self.shadow) and all(
            not 0 <= at < size or list.__getitem__(self, at) is self.shadow[at]
            for at in positions
        )
        if not matches:
            self.expression = None
        return matches

    def holds(self, name: str, *positions: int) -> bool:
        """Whether the form still describes the list, naming ``name`` when it just stopped.

        A list already plain records nothing: a plain list's operations are Python's own.
        """
        if self.expression is None:
            return False
        if self.current(*positions):
            return True
        self.sink.append(Downgrade(name=name))
        return False

    def lose(self, name: str) -> None:
        """The list turns plain, and the line names the operation that lost it."""
        self.expression = None
        self.sink.append(Downgrade(name=name))

    def static(self) -> bool:
        """Whether the form names an argument's list as it came (see ``is_static``)."""
        return self.expression is not None and is_static(self.expression)

    def derived(self, items: list[object], shadow: list[object], expression: Expression) -> ListState:
        """A new tracked list built from this one: the items, what pyct saw of them, the form."""
        made = type(self).made(items, expression, self.sink)
        made.shadow = shadow
        made.kinds = self.kinds
        return made

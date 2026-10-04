"""What a tracked list keeps beside its items: its form, its sink, and what pyct last saw.

A tracked list is a real list, so C code reads its items where they are. Beside them it keeps
the Python expression that builds it from the arguments (a-changed-list-prints-as-python-builds-it),
the kinds of the items that form can hand out, and a shadow: the items as pyct last saw them, one
per position. Code that changes the list without its methods, `heapq.heappush` say, leaves the
shadow behind, and the next operation that reads a position or the length sees it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, Self

from pyct.core.bools import ConcolicBool
from pyct.core.branch import BranchSink, Downgrade, Expression, caller_site
from pyct.core.ints import ConcolicInt
from pyct.core.spans import UNKNOWN, Span, exactly, measured
from pyct.core.str_splits import built_from_a_split, kept_form
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


def enter_kind(cls: type, kind: str) -> None:
    """Enter a tracked container type under the kind its values are: a module that defines one
    enters it when it is imported, before any value of it is built."""
    _KINDS[cls] = kind


def kind_of(item: object) -> str:
    """The kind of one item: what the solver keeps for it at its position."""
    kind = _KINDS.get(type(item))
    if kind is not None:
        return kind
    return "list" if isinstance(item, ListState) else "other"


def kinds_of(items: Iterable[object]) -> frozenset[str]:
    """The kinds of every item, as a set."""
    return frozenset(map(kind_of, items))


# each tracked scalar's plain value, read from its base type so nothing is recorded
_PLAIN: dict[type, Callable[[Any], object]] = {
    ConcolicInt: int.__int__,
    ConcolicStr: str.__str__,
    ConcolicBool: int.__bool__,
}


def plain(value: object) -> object:
    """A tracked int, str or bool as the plain value it is; any other value as it is."""
    read = _PLAIN.get(type(value))
    return value if read is None else read(value)


def plain_items(value: object) -> object:
    """A value a downgrade hands out, plain: a tracked scalar as its value, and a list Python
    built, plain `list` and nothing else, with its scalars plain in place. A list inside keeps
    its identity, since the target may change it where it sits."""
    if type(value) is list:
        list.__setitem__(value, slice(None), [plain(item) for item in value])
        return value
    return plain(value)


def is_read(expression: Expression) -> bool:
    """Whether a list's form reads an argument's list as it came: a parameter, or reads of one,
    each at a position or a key the target wrote, plain or tracked."""
    step = expression
    while isinstance(step, list):
        if len(step) != 3 or step[0] != "[]":
            return False
        step = step[1]
    return isinstance(step, str) and not step.startswith(("'", '"'))


class ListState(list):
    """The state a tracked list keeps beside its items, and what every operation checks first.

    ``expression`` is None once the list is plain: a change pyct could not write, or one made
    without the list's methods, left the form behind for good. The list refuses a set, as a
    plain one does, so pyct writes these fields straight into its ``__dict__``.
    """

    expression: Expression | None
    sink: BranchSink
    shadow: list[object]
    kinds: frozenset[str]
    # the caller's frame and instruction when a walk last started, so Python's own guess at the
    # length that follows it in the same call is not taken for the target's `len`
    walked_at: tuple[int, int] | None
    # the fewest and the most items the list holds on every input that takes the path, from how
    # it was built and the forks on its length (see ``core.spans``), and whether a change pyct
    # follows without a fork, whose effect on the length may differ on another input, made it:
    # the range of a marked list starts over at each change
    span: Span
    marked: bool

    @classmethod
    def made(cls, items: list[object], expression: Expression | None, sink: BranchSink) -> Self:
        """A tracked list of these items and this form, its shadow the items themselves."""
        # list's own, since the class called with a value builds a plain list
        made = list.__new__(cls)
        list.extend(made, items)
        fields = made.__dict__
        fields["sink"] = sink
        fields["shadow"] = list(items)
        fields["expression"] = expression
        fields["kinds"] = kinds_of(items)
        fields["walked_at"] = None
        fields["span"] = UNKNOWN
        fields["marked"] = False
        return made

    def length(self) -> int:
        """The number of items, as C code reads it: not `len`, which records `__len__`."""
        return list.__len__(self)

    def storage(self) -> list[object]:
        """The items as a plain list, read in C without walking them."""
        return list.copy(self)

    def current(self, *positions: int) -> bool:
        """Whether the form still describes the list: its length and each position read.

        One whose items were changed without its methods turns plain here, so no fork reads a
        form that no longer matches. ``holds`` asks it only of a list that has a form.
        """
        size = self.length()
        matches = size == len(self.shadow) and all(
            not 0 <= at < size or list.__getitem__(self, at) is self.shadow[at] for at in positions
        )
        if not matches:
            self.turn_plain()
        return matches

    def holds(self, name: str, *positions: int) -> bool:
        """Whether the form still describes the list, naming ``name`` when it just stopped.

        A list already plain records nothing: a plain list's operations are Python's own.
        """
        if self.expression is None:
            return False
        if self.current(*positions):
            return True
        self.sink.append(Downgrade(name=name, site=caller_site()))
        return False

    def lose(self, name: str) -> None:
        """The list turns plain, and the line names the operation that lost it."""
        self.turn_plain()
        self.sink.append(Downgrade(name=name, site=caller_site()))

    def leave_the_split(self) -> bool:
        """Whether this is a split's list, which then leaves the split's machinery for Python's
        own list, as origin/v2 hands it back: its pieces stay tracked, and the list records
        nothing more."""
        if not built_from_a_split(self.expression):
            return False
        self.__dict__["expression"] = None
        return True

    def turn_plain(self) -> None:
        """Drop the form, and with it the conditions of the items the arguments put here.

        The list is plain from now on, so what it holds is plain too: each tracked int, str
        and bool is its value, and a list inside, tracked in its own right, stays where it is.
        """
        self.__dict__["expression"] = None
        list.__setitem__(self, slice(None), [plain(item) for item in list.copy(self)])

    def derived(
        self, items: list[object], shadow: list[object], expression: Expression, span: Span
    ) -> ListState:
        """A new tracked list built from this one: the items, what pyct saw of them, the form,
        and the range that form holds. It carries this one's mark."""
        made = type(self).made(items, kept_form(expression), self.sink)
        fields = made.__dict__
        fields["shadow"] = shadow
        fields["kinds"] = self.kinds
        fields["span"] = span
        fields["marked"] = self.marked
        return made

    def measure(
        self, op: str, number: int, taken: bool, name: str = "__bool__", *, raising: bool = False
    ) -> bool:
        """Record a check on the list's length, `[op, ["len", items], n]`: a fact where its range
        proves the side Python took, else a fork, which narrows the range. Answer that side."""
        check: list[Expression] = [op, ["len", self.expression], number]
        return measured(self, check, taken, name, raising=raising)

    def resized(self, span: Span) -> None:
        """Take the range a change leaves the list: ``span``, or none at all once it is marked."""
        self.__dict__["span"] = UNKNOWN if self.marked else span

    def mark(self) -> None:
        """Note a change pyct follows without a fork, whose effect on the length may differ on
        another input that takes the path: the range starts over, here and at each change."""
        fields = self.__dict__
        fields["marked"] = True
        fields["span"] = UNKNOWN

    def span_of(self, other: list[object]) -> Span:
        """The range of a list this one takes in: a tracked list's own while its form holds and
        it is on this path, any other list's the items it holds now, which its display writes.
        A tracked list kept from an earlier call carries that call's path, so it knows nothing
        here."""
        if not isinstance(other, ListState) or other.expression is None:
            return exactly(list.__len__(other))
        return other.span if other.sink is self.sink else UNKNOWN

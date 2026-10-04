"""The concolic list: a real list that also carries the Python expression that builds it.

The `ConcolicList` body below is the taught set: indexing and slicing, the walks, the truth
test, the searches and compares, and every change a list's own methods make, each followed as
follow-lists-and-dicts-as-they-change says. What is left to list on purpose is named in
`_KEPT`, and the derivation at the bottom of the file downgrades every other method list
defines, and the `__str__` and `__format__` it inherits from object.
"""

from __future__ import annotations

import copy
import operator
from collections.abc import Callable
from typing import Any

from pyct.core import list_changes as changes
from pyct.core import list_compares as compares
from pyct.core import list_reads as reads
from pyct.core import spans, str_splits
from pyct.core.branch import Downgrade, Expression, caller_site
from pyct.core.list_forms import sliced
from pyct.core.list_state import ListState, plain, plain_items
from pyct.core.values import (
    REPORTED_CLASS,
    as_base,
    downgrade_the_rest,
    downgraded,
    own,
    refused_delete,
    refused_set,
)

# not the target's path: `__repr__`, the object plumbing, and `__init__`, which a target calls
# only to fill the list anew, a change made without the methods that the next operation
# notices. `__getattribute__` is kept because the downgrade wrapper reads `self.sink` through it
_KEPT = ("__repr__", "__getattribute__", "__init__", "__sizeof__", "__class_getitem__")

# list inherits these from object, so reading what list itself defines never reaches them, and
# `print(items)` still drops the condition
_INHERITED = ("__str__", "__format__")

# the method each compare runs, by its operator
_OPERATORS = {"==": "eq", "!=": "ne", "<": "lt", "<=": "le", ">": "gt", ">=": "ge"}


def _python(self: ListState, name: str, *args: object) -> object:
    """list's own answer, plain: a downgrade named ``name`` while the list has a form."""
    if self.expression is not None:
        return plain_items(downgraded(list, name)(self, *args))
    return plain_items(own(getattr(list, name), self, *args))


def _slice(self: ListState, key: slice) -> object:
    """``items[a:b]``, a step of 1 or -1 written as a third bound: a tracked list.

    A slice clamps to the list, so it records no fork. ``items[:]`` is the list's own form.
    """
    step = None if key.step is None else changes.position(key.step)
    bounds = changes.slice_bounds(slice(key.start, key.stop))
    if bounds is None or step not in (None, 1, -1):
        return _python(self, "__getitem__", key)
    if bounds == (None, None) and step in (None, 1):
        return self.derived(self.storage(), list(self.shadow), self.expression, self.span)
    form = sliced(self.expression, *bounds)
    if step is not None:
        form = [*form, step]
    shadow = list.__getitem__(self.shadow, key)
    return self.derived(list.__getitem__(self, key), shadow, form, _cut_span(self, bounds, step))


def _cut_span(self: ListState, bounds: tuple[Expression, Expression], step: object) -> spans.Span:
    """The range of a slice: Python's clamp of the list's range for plain bounds, and none from
    the form for a tracked one, which may cut another number of items on another input."""
    plain = changes.plain_bounds(bounds)
    if plain is None:
        return spans.UNKNOWN
    assert step is None or type(step) is int
    return spans.sliced(self.span, *plain, step)


def _item(self: ListState, key: object) -> object:
    """``items[i]``, handed out as indexed once the long-enough fork is recorded, or a slice.

    A key pyct does not follow, a slice step other than 1 or -1 or a tracked index into a list
    whose items are not all one kind, is list's own answer and a `__getitem__` downgrade.
    """
    if not self.holds("__getitem__"):
        return own(list.__getitem__, self, key)
    if isinstance(key, slice):
        return _slice(self, key)
    if not changes.follows(self, key):
        return _python(self, "__getitem__", key)
    if not changes.in_range(self, key):
        return own(list.__getitem__, self, key)
    at = changes.resolved(self, key)
    if not self.holds("__getitem__", at):
        return own(list.__getitem__, self, key)
    return reads.handed(self, at, changes.position(key), "__getitem__")


def _found(self: ListState, value: object, name: str) -> list[int] | None:
    """Where a search finds ``value``, or None when Python searches: a plain list, or a split's
    list (``_python_s_search``)."""
    if _python_s_search(self) or not self.holds(name):
        return None
    return compares.searched(self, value, name)


def _contains(self: ListState, value: object) -> bool:
    """``x in items``: each item in turn compared with ``x``, as Python compares them."""
    found = _found(self, value, "__contains__")
    return own(list.__contains__, self, value) if found is None else bool(found)


def _index(self: ListState, value: object, *bounds: object) -> object:
    """``items.index(x)``: the first position ``x`` is found at; a start or a stop is list's own."""
    if bounds:
        return _python(self, "index", value, *bounds)
    found = _found(self, value, "index")
    if found is None:
        return own(list.index, self, value)
    return found[0] if found else own(list.index, [], value)


def _python_s_search(self: ListState) -> bool:
    """Whether a search of the list is Python's own: a split's list is searched as origin/v2
    searches its plain list of pieces, each piece's compare recorded and no fork on how many
    pieces there are, by the user's decision on review round 10, as the target's own loop."""
    return str_splits.a_split_s_list(self.expression)


def _count(self: ListState, value: object) -> int:
    """``items.count(x)``: every item compared with ``x``."""
    if _python_s_search(self) or not self.holds("count"):
        return own(list.count, self, value)
    return len(compares.searched(self, value, "count", every=True))


def _remove(self: ListState, value: object) -> None:
    """``items.remove(x)``: the compares, then the change, or ValueError where Python raises.
    A split's list is Python's own from the remove on (``ListState.leave_the_split``)."""
    if self.leave_the_split():
        own(list.remove, self, value)
        return
    found = _found(self, value, "remove")
    if found is None or self.expression is None:
        own(list.remove, self, value)
        return
    changes.remove(self, value, found[0] if found else None)


def _compare(op: str) -> Callable[[ListState, object], object]:
    """One compare with another list, as Python compares two lists. Any other value is
    NotImplemented, as it is for list."""
    name = f"__{_OPERATORS[op]}__"
    operation = getattr(operator, _OPERATORS[op])

    def compute(self: ListState, other: object) -> object:
        if not isinstance(other, list):
            return NotImplemented
        if not self.holds(name):
            return own(operation, list.copy(self), other)
        if op in ("==", "!="):
            return compares.equal(self, other, name) is (op == "==")
        return compares.ordered(self, other, op)

    return compute


def _seen(other: list[object]) -> list[object]:
    """What pyct saw of another list: its shadow while tracked, else its items."""
    if isinstance(other, ListState) and other.expression is not None:
        return other.shadow
    return list.copy(other)


def _joined(self: ListState, other: object, name: str, *, reflected: bool = False) -> object:
    """``items + ys``, or ``ys + items`` when ``reflected``, with a list ``ys``: a tracked list.

    Any other value is NotImplemented, as it is for list, so Python raises its own TypeError.
    """
    if not isinstance(other, list):
        return NotImplemented
    if str_splits.a_split_s_list(self.expression) and isinstance(other, ListState):
        # a split's list joined with another tracked list is that list's join with a plain list
        # of the pieces, as origin/v2's plain list of pieces makes it, and two splits' lists
        # joined are two plain lists joined
        if str_splits.a_split_s_list(other.expression):
            left, right = (other, self) if reflected else (self, other)
            return list.copy(left) + list.copy(right)
        return _joined(other, list.copy(self), name, reflected=not reflected)
    taken = changes.added(other, name) if self.holds(name) else None
    if taken is None:
        left, right = (other, self) if reflected else (self, other)
        return _python_joined(self, name, list.copy(left), list.copy(right))
    form, kinds = taken
    sides = [(self.expression, self.storage(), self.shadow), (form, list.copy(other), _seen(other))]
    if reflected:
        sides.reverse()
    (left_form, left, left_seen), (right_form, right, right_seen) = sides
    span = spans.added(self.span, self.span_of(other))
    made = self.derived(left + right, left_seen + right_seen, ["+", left_form, right_form], span)
    fields = made.__dict__
    fields["kinds"] = self.kinds | kinds
    if isinstance(other, ListState) and other.marked:
        made.mark()
    return made


def _python_joined(self: ListState, name: str, left: list[object], right: list[object]) -> object:
    """Two lists joined as Python joins them, plain, the loss named while the list has a form."""
    if self.expression is not None:
        self.sink.append(Downgrade(name=name, site=caller_site()))
    return plain_items(left + right)


def _repeated(self: ListState, count: object, name: str, *, reflected: bool = False) -> object:
    """``items * k`` or ``k * items`` with a plain int ``k``: a tracked list.

    A tracked or other count Python takes is its own answer and a downgrade; any other value
    is NotImplemented, as it is for list.
    """
    times = reads.plain_index(count)
    if times is None:
        if not hasattr(type(count), "__index__"):
            return NotImplemented
        return _python(self, "__mul__" if not reflected else "__rmul__", count)
    if not self.holds(name):
        return own(list.__mul__, list.copy(self), times)
    form = ["*", times, self.expression] if reflected else ["*", self.expression, times]
    span = spans.repeated(self.span, times)
    return self.derived(self.storage() * times, self.shadow * times, form, span)


def _copied(self: ListState) -> object:
    """``items.copy()`` and ``copy.copy(items)``: a tracked list with the same form."""
    if not self.holds("copy"):
        return own(list.copy, self)
    return self.derived(self.storage(), list(self.shadow), self.expression, self.span)


def _deep_copied(self: ListState, memo: dict[int, object]) -> object:
    """``copy.deepcopy(items)``: the same form over copies of the items.

    Every position is checked first, since the copy's own shadow is the copies it makes.
    """
    followed = self.holds("__deepcopy__", *range(self.length()))
    made = self.derived([], [], self.expression, self.span) if followed else []
    memo[id(self)] = made
    items = [copy.deepcopy(item, memo) for item in self.storage()]
    list.extend(made, items)
    if isinstance(made, ListState):
        made.__dict__["shadow"] = list(items)
    return made


def _sorted(self: ListState, *args: object, **kwargs: object) -> None:
    """``items.sort()``, with a key and reverse or not: a display of the items in their new order.

    The items are taken by a walk, and Python's own sort compares them, each compare of tracked
    items a fork. The list becomes ``[items[1], items[0]]`` say.
    """
    if self.leave_the_split() or args or set(kwargs) - {"key", "reverse"} or not self.holds("sort"):
        own(list.sort, self, *args, **kwargs)
        return
    items = list(reads.walk(self))
    key: Any = kwargs.get("key")
    keys: list[Any] = items if key is None else [own(key, item) for item in items]
    placed: list[int] = own(
        sorted, range(len(items)), key=keys.__getitem__, reverse=bool(kwargs.get("reverse"))
    )
    storage, shadow = self.storage(), self.shadow
    list.__setitem__(self, slice(None), [storage[at] for at in placed])
    fields = self.__dict__
    fields["shadow"] = [shadow[at] for at in placed]
    fields["expression"] = ["[,]", *(["[]", self.expression, at] for at in placed)]
    # a display holds exactly its items, as many as the walk took
    self.resized(spans.exactly(len(placed)))


def _truth(self: ListState) -> bool:
    """``if items:``: Python tests a list by its length, so the check is `len(items) != 0`, a fact
    where the list's range proves it, else a fork."""
    if not self.holds("__bool__"):
        return self.length() != 0
    return self.measure("!=", 0, self.length() != 0)


def _size(self: ListState) -> int:
    """``items.__len__()``: Python's `len` makes the answer plain before the target sees it, so
    it is a downgrade, but for the size a walk just started asks for (see `reads.hinted`). A
    `len(items)` in the target's package asks pyct's own `len`, which gives the list's length
    term (`reads.length`)."""
    if self.expression is not None and not reads.hinted(self):
        self.sink.append(Downgrade(name="__len__", site=caller_site()))
    return self.length()


def _pickled(self: ListState, protocol: object) -> object:
    """A pickle of a tracked list holds the plain list: pickle-holds-the-plain-value."""
    if self.expression is not None:
        self.sink.append(Downgrade(name="__reduce_ex__", site=caller_site()))
    return (list, ([plain(item) for item in self.storage()],))


def _iadd(self: ListState, values: object) -> object:
    if isinstance(values, ListState) and changes.takes_another(self, values):
        # origin/v2's plain list of pieces has no `__iadd__`, so Python hands `+=` to the
        # tracked list's `__radd__`, a new tracked list
        return _joined(values, list.copy(self), "__radd__", reflected=True)
    changes.extend(self, values, "__iadd__")
    return self


def _imul(self: ListState, count: object) -> ListState:
    changes.repeat(self, count, "__imul__")
    return self


class ConcolicList(ListState):
    """A real list with a form, a sink, and a shadow of the items pyct saw.

    The operations taught below stay symbolic. Any other method list defines, except those left
    to it in `_KEPT`, is list's own and returns a plain value, with a downgrade in the sink
    naming what was lost (``README.md › Rules › downgrades``).
    """

    # the base type, as `isinstance`, singledispatch and a class pattern read it; the class
    # called with a value is list's own, a plain list, since pyct builds one through `made`
    __class__ = REPORTED_CLASS  # pyrefly: ignore[bad-override]
    __new__ = as_base
    # a plain list takes no attribute: a set or a delete is Python's own refusal, pyct's names too
    __setattr__ = refused_set
    __delattr__ = refused_delete

    # the form's reads and walks: an index records whether the list is long enough first
    __getitem__ = _item  # pyrefly: ignore[bad-override]
    __iter__ = reads.walk  # pyrefly: ignore[bad-override]
    __reversed__ = reads.backward  # pyrefly: ignore[bad-override]
    __bool__ = _truth
    __len__ = _size

    # the searches and the compares, each item compared as Python compares them. list promises
    # a bool from a compare, and an order answers with the pair's own compare, as Python's does
    __contains__ = _contains  # pyrefly: ignore[bad-override]
    index = _index  # pyrefly: ignore[bad-override]
    count = _count  # pyrefly: ignore[bad-override]
    __eq__ = _compare("==")  # pyrefly: ignore[bad-override]
    __ne__ = _compare("!=")  # pyrefly: ignore[bad-override]
    __lt__ = _compare("<")  # pyrefly: ignore[bad-override]
    __le__ = _compare("<=")  # pyrefly: ignore[bad-override]
    __gt__ = _compare(">")  # pyrefly: ignore[bad-override]
    __ge__ = _compare(">=")  # pyrefly: ignore[bad-override]
    __hash__ = None

    # the lists it builds, each tracked with the form that builds it
    __add__ = lambda self, other: _joined(self, other, "__add__")  # pyrefly: ignore[bad-override]  # noqa: E731
    __radd__ = lambda self, other: _joined(self, other, "__radd__", reflected=True)  # noqa: E731
    __mul__ = lambda self, count: _repeated(self, count, "__mul__")  # pyrefly: ignore[bad-override]  # noqa: E731
    __rmul__ = lambda self, count: _repeated(self, count, "__rmul__", reflected=True)  # pyrefly: ignore[bad-override]  # noqa: E731
    copy = _copied  # pyrefly: ignore[bad-override]
    __copy__ = _copied
    __deepcopy__ = _deep_copied
    __reduce_ex__ = _pickled  # pyrefly: ignore[bad-override]

    # the changes, each writing the form it leaves behind
    __setitem__ = changes.assign  # pyrefly: ignore[bad-override]
    __delitem__ = changes.delete  # pyrefly: ignore[bad-override]
    __iadd__ = _iadd  # pyrefly: ignore[bad-override]
    __imul__ = _imul  # pyrefly: ignore[bad-override]
    append = changes.append  # pyrefly: ignore[bad-override]
    extend = changes.extend  # pyrefly: ignore[bad-override]
    insert = changes.insert  # pyrefly: ignore[bad-override]
    pop = changes.pop  # pyrefly: ignore[bad-override]
    remove = _remove  # pyrefly: ignore[bad-override]
    clear = changes.clear  # pyrefly: ignore[bad-override]
    reverse = changes.reverse  # pyrefly: ignore[bad-override]
    sort = _sorted  # pyrefly: ignore[bad-override]


# the class body above is everything ConcolicList teaches. The rest of list, and the `__str__`
# and `__format__` it inherits, differ only in the name they call and record, so the derivation
# writes them
downgrade_the_rest(ConcolicList, list, kept=_KEPT, inherited=_INHERITED)

# a split hands back its pieces in a tracked list (follow-the-length-of-a-split)
str_splits.enter_list(ConcolicList)

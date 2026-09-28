"""What intercepted code calls: `is`, `in`, conversions, a str literal's method, an operator
with a float or bool literal on the left, or a name bound only to one, the value a `__bool__`
method returns, and `len`, `ord`, `chr`.

`pyct.intercept` substitutes an operation the target writes with a call of
one of these functions, through a name it binds in the module, such as
``__pyct_in__``, handing over the same operands in the same order. Python
answers `is` without asking either operand, tests the answer of `in` for
truth before the target sees it, copies a conversion's answer into a plain
number, never calls a method of a tracked str handed to a str literal's
method, and lets a float or bool on the left answer an operator before a
tracked int on the right is asked, so a tracked value would lose its
condition in each; and it refuses a tracked bool returned from `__bool__`,
where the target would stop. Here a tracked value answers as it stands for, and any
other operand gets Python's own answer and Python's own exception. Inside
a chained compare, where each operand is evaluated once on Python's stack,
the link keeps Python's own `in` and searches a container of this module's,
`Searched` or `Identity`, which asks the same functions.

A call written `int(...)`, `float(...)`, `bool(...)`, `map(...)`,
`range(...)`, or `type(...)` with one argument, and a call of a `math`
function through a name the module binds to it (`pyct.intercept.constants`),
asks `call` for its callee first, and calls what it hands back: pyct's
router for Python's own function, which `pyct.core.bound` holds beside the
`len`, `ord` and `chr` it binds in the module's builtins, and the callee
itself for anything else, so a function of the target's runs with no frame
of pyct's above it. An operator's right side goes through `handed`
(`pyct.core.handed`) before Python's own operator runs, so no frame of
pyct's is above the target's own operator either.

Each function is a router: it picks which answer to give and calls Python
or core for it, and runs none of the target's code in its own lines. So
blame reads through its frame (`PASSING`): a raise under it is the target's
unless one of core's own frames sits below.
"""

from __future__ import annotations

import operator
import types
from collections import deque
from collections.abc import Callable, Iterator
from typing import Any, cast

from pyct.core import bound, ranges, str_joins, str_literals, strs
from pyct.core.bases import TRACKED_CLASSES
from pyct.core.bools import ConcolicBool
from pyct.core.floats import ConcolicFloat
from pyct.core.handed import PASSING as HANDED_PASSING
from pyct.core.handed import handed as handed  # substituted modules import it from here
from pyct.core.hashed import Tracked, hashed, looked_up, tracked
from pyct.core.ints import ConcolicInt
from pyct.core.ranges import ConcolicRange
from pyct.core.strs import ConcolicStr

# the tracked ints and bools, by their exact type: a plain range is searched for one with one
# fork
_INT_ITEMS = frozenset(ranges.TRACKED_INTS)
# the containers Python searches element by element, identity first, then `==` with the element
# on the left
_WALKED: tuple[type, ...] = (tuple, list, deque)
# for each tracked type, the plain types whose own `==` answers it plainly from the element's
# left: an int's and a float's for a tracked int or bool, a float's for a tracked float, and a
# str's for a tracked str
_ANSWERED_PLAINLY: dict[type, tuple[type, ...]] = {
    ConcolicBool: (int, float),
    ConcolicInt: (int, float),
    ConcolicFloat: (float,),
    ConcolicStr: (str,),
}


def _stands_for(value: object, other: object) -> bool:
    """Whether `value is other` asks which bool a tracked bool stands for."""
    return isinstance(value, ConcolicBool) and (other is True or other is False)


def is_(left: object, right: object) -> bool:
    """`left is right`, with a tracked bool against True or False read as the bool it stands for.

    Testing the tracked bool for truth records its fork, as `if b:` would,
    where the `is` runs. Two tracked bools stand for two of the two bool
    singletons, so they are the same object when they are equal, and the
    fork is their `==`. Any other pair is Python's own identity.
    """
    if isinstance(left, ConcolicBool) and isinstance(right, ConcolicBool) and left is not right:
        return bool(left == right)
    if _stands_for(left, right):
        return bool(left) is right
    if _stands_for(right, left):
        return left is bool(right)
    return left is right


def is_not(left: object, right: object) -> bool:
    """`left is not right`: the negation of `is_`, with the same fork."""
    return not is_(left, right)


def in_(item: object, container: object, written: tuple[object, ...] | None = None) -> object:
    """`item in container`, handing back a tracked answer where a tracked value can give one.

    A tracked string answers with its condition untested, so the fork is
    recorded where the target tests it, as a compare's is. A tracked string
    searched in a plain one does the same with the plain one as a literal.
    ``written`` holds the literal elements of a set, or the literal keys of
    a dict, in the order the display writes them: a tracked value is
    searched for there, one `==` fork per element tried (see `_searched`).
    A tracked range, or a tracked int searched in a plain range, answers
    with one condition untested (`pyct.core.ranges`), where Python alone
    would compare a tracked int with every element in turn. A tracked value
    in a set, a frozenset or a dict's keys is searched for as
    `pyct.core.hashed` says, and one in a tuple, a list or a deque as
    `_walked` says. Anything else is Python's own `in`.
    """
    if isinstance(container, ConcolicStr):
        return type(container).__contains__(container, item)
    if type(container) is str and isinstance(item, ConcolicStr):
        return strs.in_text(item, container)
    if type(container) is ConcolicRange:
        return ranges.contains(container, item)
    if tracked(item):
        return _tracked_in(item, container, written)
    # any value, as Python's own `in` takes, raising what Python raises for one it cannot search
    return item in container  # pyrefly: ignore[not-iterable]


def _searched(item: object, written: tuple[object, ...]) -> bool:
    """Whether the tracked item equals one of the literal elements, tried in the order written.

    Python's answer, as a tuple of the same elements gives it, and the same
    stop at the first element that holds. The tracked item is on the left of
    each `==`, so it answers and its fork is recorded, as `b == True` records
    it; with the literal on the left, a plain `True` would answer a tracked
    bool, which is an int to it, and record nothing.
    """
    return any(item == element for element in written)


def not_in(item: object, container: object, written: tuple[object, ...] | None = None) -> object:
    """`item not in container`, by the rules of `in_`, with `not in` as its own head on strings.

    A literal display records the same `==` forks as `in_`.
    """
    if isinstance(container, ConcolicStr):
        return strs.not_contains(container, item)
    if type(container) is str and isinstance(item, ConcolicStr):
        return strs.not_in_text(item, container)
    if type(container) is ConcolicRange:
        return ranges.not_contains(container, item)
    if tracked(item):
        if type(container) is range and type(item) in _INT_ITEMS:
            return ranges.not_within(item, container)  # pyrefly: ignore[bad-argument-type]
        return not _tracked_in(item, container, written)
    return item not in container  # pyrefly: ignore[not-iterable]


def _tracked_in(item: Tracked, container: object, written: tuple[object, ...] | None) -> object:
    """`item in container` for a tracked item a set or a dict can hold: one fork in a plain
    range, one `==` fork per literal element of a display, a lookup in a hashed container, a
    walk of a tuple, a list or a deque, and Python's own `in` for anything else."""
    if type(container) is range and type(item) in _INT_ITEMS:
        return ranges.within(item, container)  # pyrefly: ignore[bad-argument-type]
    if written is not None:
        return _searched(item, written)
    if (kind := hashed(container)) is not None:
        return looked_up(item, container, kind)
    if (kind := _sequence(container)) is not None:
        return _walked(item, kind.__iter__(container))
    return item in container  # pyrefly: ignore[not-iterable]


def _sequence(container: object) -> type | None:
    """The type Python searches the container as element by element, a tuple, a list or a
    deque, or None for any other container.

    A subclass counts when it keeps its base's own `__contains__`, as a
    named tuple does; one that defines its own is asked, as Python asks it.
    """
    own_type: type[Any] = type(container)
    for kind in _WALKED:
        if issubclass(own_type, kind):
            return kind if own_type.__contains__ is kind.__contains__ else None
    return None


def _walked(item: Tracked, elements: Iterator[object]) -> bool:
    """Whether the tracked value is one of the elements, as Python's `in` answers on a tuple, a
    list or a deque: in order, identity first, then `==`, until one holds.

    Python puts the element on the left of each `==`. An element whose
    type keeps the own `__eq__` of a type `_ANSWERED_PLAINLY` names for the
    tracked value, an IntEnum member or True beside a tracked int, a float
    beside a tracked int, a float-valued Enum member beside a tracked float,
    a StrEnum member beside a tracked str, then answers plainly, since the
    tracked value is no subclass of its type, and the condition is lost; so
    the tracked value is put on the left of every such element, an exact
    int, float or str included, and answers with the same bool and a fork,
    the element written as its plain value. Any other element is compared as Python compares it, so an
    element with its own `__eq__` answers first. The base type's own walk
    is read, so a subclass's `__iter__` never runs where Python's `in` would
    not run it, and a deque changed during the walk raises as its own
    search does.
    """
    bases = _ANSWERED_PLAINLY.get(type(item), ())
    for element in elements:
        if element is item:
            return True
        if _answers_plainly(element, bases):
            if item == element:
                return True
        elif element == item:
            return True
    return False


def _answers_plainly(element: object, bases: tuple[type, ...]) -> bool:
    """Whether the element is of one of the base types and its type keeps that base's own
    `__eq__`."""
    eq = type(element).__eq__
    return any(eq is base.__eq__ and isinstance(element, base) for base in bases)


def _forwarded(compare: Callable[[Any, Any], object]) -> Callable[[_Link, object], object]:
    """A rich compare of the operand a link holds, as Python runs it on the operand itself."""

    def forward(self: _Link, other: object) -> object:
        return compare(self.held, other)

    return forward


class _Link:
    """An operand of a chained compare that pyct's `in` searches, handed to the next link.

    CPython holds each operand of a chain once, on its stack, and hands it
    to the next link as that link's left. So a link after this one sees it:
    a compare runs on the operand it holds, as Python runs it, and a link
    of pyct's own reads the operand it holds (`_unlinked`).
    """

    __slots__ = ("held",)

    def __init__(self, held: object) -> None:
        self.held = held

    __lt__ = _forwarded(operator.lt)
    __le__ = _forwarded(operator.le)
    __gt__ = _forwarded(operator.gt)
    __ge__ = _forwarded(operator.ge)
    __eq__ = _forwarded(operator.eq)  # pyrefly: ignore[bad-override]
    __ne__ = _forwarded(operator.ne)  # pyrefly: ignore[bad-override]


def _unlinked(item: object) -> object:
    """The operand a link holds, where the link before handed one on; any other item itself."""
    return item.held if isinstance(item, _Link) else item


class Searched(_Link):
    """The container a chained compare's `in` link searches, as `in_` searches it.

    Python's own `in` asks it with the item, so the chain keeps its stack,
    each operand evaluated once, and the fork is recorded at the chain's
    own position. ``written`` is `in_`'s.
    """

    __slots__ = ("written",)

    def __init__(self, held: object, written: tuple[object, ...] | None = None) -> None:
        super().__init__(held)
        self.written = written

    def __contains__(self, item: object) -> object:
        # Python tests the answer for truth itself, which records a tracked answer's fork here
        return in_(_unlinked(item), self.held, self.written)


class Identity(_Link):
    """The right operand a chained compare's `is` link meets, answered as `is_` answers it."""

    __slots__ = ()

    def __contains__(self, item: object) -> bool:
        return is_(_unlinked(item), self.held)


def call(callee: object, /) -> Any:
    """What a call written `int(...)`, `float(...)`, `bool(...)`, `map(...)`, `range(...)` or
    `type(...)` calls, and a call of a `math` function through a name the module binds to it.

    ``callee`` is what the name the code wrote holds when the call runs.
    Python's own builtin gets pyct's router for it (`bound.CALLED`), and
    anything else, a function of the target's included, is handed back to
    be called as written. Only the callee's identity is read.
    """
    router = bound.CALLED.get(id(callee))
    return callee if router is None else router


def method(receiver_method: Callable[..., object], /, *args: object, **kwargs: object) -> Any:
    """A call written ``"text".name(...)``, a str literal's method or one on a name bound only to
    str literals, as ``receiver_method(...)``.

    Given a tracked str, it runs as it runs on a tracked str holding the
    literal's text (`str_literals.on_text`). Any other call is the method's own; one
    with a keyword goes through str, as the written call reaches it, so a
    refusal reads in the written call's words. Only the types of the method,
    its receiver and the arguments are read.
    """
    for arg in args:
        if type(arg) is ConcolicStr:
            return _on_text(receiver_method, args, kwargs)
    if not kwargs:
        return receiver_method(*args)
    for arg in kwargs.values():
        if type(arg) is ConcolicStr:
            return _on_text(receiver_method, args, kwargs)
    receiver = getattr(receiver_method, "__self__", None)
    if type(receiver_method) is types.BuiltinMethodType and type(receiver) is str:
        return getattr(str, receiver_method.__name__)(receiver, *args, **kwargs)
    return receiver_method(*args, **kwargs)


def join(receiver_method: Callable[..., object], /, *args: object, **kwargs: object) -> Any:
    """A call written ``"text".join(...)``, on a str literal or a name bound only to str
    literals, as ``receiver_method(...)``.

    Given one argument, it reads what it joins once, as Python's own join
    does, and joins as a tracked separator holding the literal's text joins
    (`str_joins.joined`) when the argument or an item is tracked. Anything
    else is the method's own, handed the items read, and any other call is
    `method`'s. Only the types of the method, its receiver, the argument and
    its items are read.
    """
    if kwargs or len(args) != 1:
        return method(receiver_method, *args, **kwargs)
    items = args[0]
    if type(items) is list or type(items) is tuple:
        for item in cast("list[object]", items):
            if type(item) in TRACKED_CLASSES:
                break
        else:
            return receiver_method(items)
    # the receiver is what the name the code wrote holds when the call runs: a str literal's
    # text, unless another module rebound the name. A str or a tracked str joins as pyct follows
    # it, and any other value's own join is called as Python calls it, with what it was given
    receiver = getattr(receiver_method, "__self__", None)
    if type(receiver) is not str and type(receiver) is not ConcolicStr:
        return receiver_method(items)
    return _joined(receiver_method, cast(str, receiver), items)


def _joined(receiver_method: Callable[..., object], receiver: str, items: object) -> object:
    """A str's join of what it is given, read once: Python's own answer and refusal when
    nothing in it is tracked, and `str_joins.joined` when something is."""
    if type(items) not in TRACKED_CLASSES:
        items = _read(items)
        if items is None:
            # Python's join makes any TypeError `iter` raises its own refusal, which this raises
            return receiver_method(None)
        for item in items:
            if type(item) in TRACKED_CLASSES:
                break
        else:
            return receiver_method(items)
    return str_joins.joined(receiver, items, ConcolicStr)


def _read(items: object) -> list[object] | tuple[object] | None:
    """What a join reads, as Python's own join reads it: a list or a tuple as it is, and any
    other iterable into a list, its `__iter__` called once; None where `iter` raises TypeError."""
    if type(items) is list or type(items) is tuple:
        return cast("list[object]", items)
    try:
        iterator = iter(items)  # pyrefly: ignore[no-matching-overload]
    except TypeError:
        return None
    return list(iterator)


def _on_text(
    receiver_method: Callable[..., object], args: tuple[object, ...], kwargs: dict[str, object]
) -> Any:
    """A tracked str handed to a plain str's own method, as `str_literals.on_text` runs it."""
    receiver = getattr(receiver_method, "__self__", None)
    if type(receiver_method) is types.BuiltinMethodType and type(receiver) is str:
        return str_literals.on_text(cast(types.BuiltinMethodType, receiver_method), *args, **kwargs)
    return receiver_method(*args, **kwargs)


def truth(value: object, /) -> object:
    """The value a `return` in a `__bool__` method written in a class body hands back.

    CPython takes only an exact bool from `__bool__`, and a tracked bool is
    an int, so it is tested for truth here, which records its fork where
    the `return` runs, as `if value:` there would, and comes back the real
    bool it stands for. Any other value, a tracked int included, is handed
    back as it is, so Python raises its own TypeError for one that is not a
    bool. Only the value's type is read.
    """
    if type(value) is ConcolicBool:
        return bool(value)
    return value


# the frames blame reads through: a raise under one of them, from Python's own `in`, `len`,
# `ord`, `chr` or a conversion, or from the target's own `__contains__`, `__len__` or
# `__int__`, is the target's
PASSING: frozenset[types.CodeType] = (
    frozenset(
        function.__code__
        for function in (
            is_,
            is_not,
            in_,
            not_in,
            _tracked_in,
            _walked,
            call,
            method,
            join,
            _joined,
            _read,
            _on_text,
            truth,
            Searched.__contains__,
            Identity.__contains__,
            # the one code object all six forwarded compares share
            _Link.__lt__,
        )
    )
    | HANDED_PASSING
    | bound.PASSING
)

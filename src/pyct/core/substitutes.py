"""What intercepted code calls: `is`, `in`, conversions, a str literal's method and an operator
with a float or bool literal on the left, or a name bound only to one, and `len`, `ord`, `chr`.

`pyct.intercept` substitutes an operation the target writes with a call of
one of these functions, through a name it binds in the module, such as
``__pyct_in__``, handing over the same operands in the same order. Python
answers `is` without asking either operand, tests the answer of `in` for
truth before the target sees it, copies a conversion's answer into a plain
number, never calls a method of a tracked str handed to a str literal's
method, and lets a float or bool on the left answer an operator before a
tracked int on the right is asked, so a tracked value would lose its
condition in each. Here a tracked value answers as it stands for, and any
other operand gets Python's own answer and Python's own exception. Inside
a chained compare, where each operand is evaluated once on Python's stack,
the link keeps Python's own `in` and searches a container of this module's,
`Searched` or `Identity`, which asks the same functions.

A call written `int(...)`, `float(...)`, `bool(...)`, `map(...)` or `range(...)` asks
`call` for its callee first, and calls what it hands back: pyct's router
for Python's own builtin, which `pyct.core.bound` holds beside the `len`,
`ord` and `chr` it binds in the module's builtins, and the callee itself for
anything else, so a function of the target's runs with no frame of pyct's
above it. An operator's right side goes through `handed` (`pyct.core.handed`)
before Python's own operator runs, so no frame of pyct's is above the
target's own operator either.

Each function is a router: it picks which answer to give and calls Python
or core for it, and runs none of the target's code in its own lines. So
blame reads through its frame (`PASSING`): a raise under it is the target's
unless one of core's own frames sits below.
"""

from __future__ import annotations

import operator
import types
from collections.abc import Callable
from typing import Any, cast

from pyct.core import bound, ranges, str_literals, strs
from pyct.core.bools import ConcolicBool
from pyct.core.handed import PASSING as HANDED_PASSING
from pyct.core.handed import handed as handed  # substituted modules import it from here
from pyct.core.hashed import Tracked, hashed, looked_up, tracked
from pyct.core.ranges import ConcolicRange
from pyct.core.strs import ConcolicStr

# the tracked values a plain range is searched for with one fork, by their exact type
_RANGE_ITEMS = frozenset(ranges.TRACKED_INTS)


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
    `pyct.core.hashed` says. Anything else is Python's own `in`.
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
        if type(container) is range and type(item) in _RANGE_ITEMS:
            return ranges.not_within(item, container)  # pyrefly: ignore[bad-argument-type]
        return not _tracked_in(item, container, written)
    return item not in container  # pyrefly: ignore[not-iterable]


def _tracked_in(item: Tracked, container: object, written: tuple[object, ...] | None) -> object:
    """`item in container` for a tracked item a set or a dict can hold: one fork in a plain
    range, one `==` fork per literal element of a display, a lookup in a hashed container, and
    Python's own `in` for anything else."""
    if type(container) is range and type(item) in _RANGE_ITEMS:
        return ranges.within(item, container)  # pyrefly: ignore[bad-argument-type]
    if written is not None:
        return _searched(item, written)
    if (kind := hashed(container)) is not None:
        return looked_up(item, container, kind)
    return item in container  # pyrefly: ignore[not-iterable]


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
    """What a call written `int(...)`, `float(...)`, `bool(...)`, `map(...)` or `range(...)`
    calls.

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


def _on_text(
    receiver_method: Callable[..., object], args: tuple[object, ...], kwargs: dict[str, object]
) -> Any:
    """A tracked str handed to a plain str's own method, as `str_literals.on_text` runs it."""
    receiver = getattr(receiver_method, "__self__", None)
    if type(receiver_method) is types.BuiltinMethodType and type(receiver) is str:
        return str_literals.on_text(cast(types.BuiltinMethodType, receiver_method), *args, **kwargs)
    return receiver_method(*args, **kwargs)


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
            call,
            method,
            _on_text,
            Searched.__contains__,
            Identity.__contains__,
            # the one code object all six forwarded compares share
            _Link.__lt__,
        )
    )
    | HANDED_PASSING
    | bound.PASSING
)

"""What intercepted code calls: `is` and `in` where the target wrote them, and `len`, `ord`, `chr`.

`pyct.intercept` substitutes a compare the target writes with a call of one
of these functions, through a name it binds in the module, such as
``__pyct_in__``, handing over the same operands in the same order. Python
answers `is` without asking either operand, and tests the answer of `in`
for truth before the target sees it, so a tracked value would lose its
condition in both. Here a tracked value
answers as it stands for, and any other operand gets Python's own answer
and Python's own exception. Inside a chained compare, where each operand
is evaluated once on Python's stack, the link keeps Python's own `in` and
searches a container of this module's, `Searched` or `Identity`, which asks
the same functions.

It also binds `len`, `ord` and `chr` in the module's builtins to the three
functions `pyct.core.bound` holds, routers of the same kind.

Each function is a router: it picks which answer to give and calls Python
or core for it, and runs none of the target's code in its own lines. So
blame reads through its frame (`PASSING`): a raise under it is the target's
unless one of core's own frames sits below.
"""

from __future__ import annotations

import operator
import types
from collections.abc import Callable
from typing import Any

from pyct.core import bound, strs
from pyct.core.bools import ConcolicBool
from pyct.core.hashed import SEARCHED_MOST, hashed, looked_up, tracked
from pyct.core.strs import ConcolicStr

__all__ = ["SEARCHED_MOST", "Identity", "Searched", "in_", "is_", "is_not", "not_in"]


def _stands_for(value: object, other: object) -> bool:
    """Whether `value is other` asks which bool a tracked bool stands for."""
    return isinstance(value, ConcolicBool) and (other is True or other is False)


def is_(left: object, right: object) -> bool:
    """`left is right`, with a tracked bool against True or False read as the bool it stands for.

    Testing the tracked bool for truth records its fork, as `if b:` would,
    where the `is` runs. Any other pair is Python's own identity.
    """
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
    A tracked value in a set, a frozenset or a dict's keys is searched for
    as `pyct.core.hashed` says. Anything else is Python's own `in`.
    """
    if isinstance(container, ConcolicStr):
        return type(container).__contains__(container, item)
    if type(container) is str and isinstance(item, ConcolicStr):
        return strs.in_text(item, container)
    if written is not None and tracked(item):
        return _searched(item, written)
    if tracked(item) and (kind := hashed(container)) is not None:
        return looked_up(item, container, kind)
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
    if written is not None and tracked(item):
        return not _searched(item, written)
    if tracked(item) and (kind := hashed(container)) is not None:
        return not looked_up(item, container, kind)
    return item not in container  # pyrefly: ignore[not-iterable]


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


# the tracked values core follows through each bound builtin, by their exact type, and the
# function that follows them. A tracked value's `__len__` stays a downgrade, since Python's own
# `len` makes its answer plain; pyct's asks core for the tracked length instead
# the frames blame reads through: a raise under one of them, from Python's own `in`, `len`,
# `ord` or `chr`, or from the target's own `__contains__` or `__len__`, is the target's
PASSING: frozenset[types.CodeType] = (
    frozenset(
        function.__code__
        for function in (
            is_,
            is_not,
            in_,
            not_in,
            Searched.__contains__,
            Identity.__contains__,
            # the one code object all six forwarded compares share
            _Link.__lt__,
        )
    )
    | bound.PASSING
)

"""What substituted code calls: `is` and `in` where the target wrote them.

`pyct.intercept` substitutes a compare the target writes with a call of one
of these functions, through a name it binds in the module, such as
``__pyct_in__``, handing over the same operands in the same order. Python
answers `is` without asking either operand, and tests the answer of `in`
for truth before the target sees it, so a tracked value would lose its
condition in both. Here a tracked value
answers as it stands for, and any other operand gets Python's own answer
and Python's own exception.

Each function is a router: it picks which answer to give and calls Python
or core for it, and runs none of the target's code in its own lines. So
blame reads through its frame (`PASSING`): a raise under it is the target's
unless one of core's own frames sits below.
"""

from __future__ import annotations

import types

from pyct.core import strs
from pyct.core.bools import ConcolicBool
from pyct.core.ints import ConcolicInt
from pyct.core.strs import ConcolicStr

# the tracked values a set or dict can hold: those a literal display is searched for, element
# by element, as a tuple of the same elements is
_HASHABLE = (ConcolicBool, ConcolicInt, ConcolicStr)


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
    searched for there, one `==` fork per element tried, as a tuple
    records. Anything else is Python's own `in`.
    """
    if isinstance(container, ConcolicStr):
        return type(container).__contains__(container, item)
    if type(container) is str and isinstance(item, ConcolicStr):
        return strs.in_text(item, container)
    if written is not None and isinstance(item, _HASHABLE):
        return item in written
    # any value, as Python's own `in` takes, raising what Python raises for one it cannot search
    return item in container  # pyrefly: ignore[not-iterable]


def not_in(item: object, container: object, written: tuple[object, ...] | None = None) -> object:
    """`item not in container`, by the rules of `in_`, with `not in` as its own head on strings.

    A literal display records the same `==` forks as `in_`.
    """
    if isinstance(container, ConcolicStr):
        return strs.not_contains(container, item)
    if type(container) is str and isinstance(item, ConcolicStr):
        return strs.not_in_text(item, container)
    if written is not None and isinstance(item, _HASHABLE):
        return item not in written
    return item not in container  # pyrefly: ignore[not-iterable]


# the frames blame reads through: a raise under one of them, from Python's own `in` or from
# the target's own `__contains__`, is the target's
PASSING: frozenset[types.CodeType] = frozenset(
    function.__code__ for function in (is_, is_not, in_, not_in)
)

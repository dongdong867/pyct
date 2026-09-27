"""What substituted code calls: `is`, `in`, conversions, a plain str's method and a plain
number's operator, where the target wrote them.

`pyct.intercept` substitutes an operation the target writes with a call of
one of these functions, through a name it binds in the module, such as
``__pyct_in__``, handing over the same operands in the same order. Python
answers `is` without asking either operand, tests the answer of `in` for
truth before the target sees it, copies a conversion's answer into a plain
number, never calls a method of a tracked str handed to a plain str's
method, and lets a plain float or bool on the left answer an operator
before a tracked int on the right is asked, so a tracked value would lose
its condition in each. Here a tracked value answers as it stands for, and
any other operand gets Python's own answer and Python's own exception.

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

from pyct.core import conversions, strs
from pyct.core.bools import ConcolicBool
from pyct.core.floats import ConcolicFloat
from pyct.core.ints import ConcolicInt
from pyct.core.strs import ConcolicStr

# the tracked values a set or dict can hold: those a literal display is searched for, element
# by element, as a tuple of the same elements is
_HASHABLE = (ConcolicBool, ConcolicInt, ConcolicFloat, ConcolicStr)


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
    Anything else is Python's own `in`.
    """
    if isinstance(container, ConcolicStr):
        return type(container).__contains__(container, item)
    if type(container) is str and isinstance(item, ConcolicStr):
        return strs.in_text(item, container)
    if written is not None and isinstance(item, _HASHABLE):
        return _searched(item, written)
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
    if written is not None and isinstance(item, _HASHABLE):
        return not _searched(item, written)
    return item not in container  # pyrefly: ignore[not-iterable]


def call(callee: Callable[..., object], /, *args: object, **kwargs: object) -> Any:
    """A call written `int(...)`, `float(...)`, `bool(...)` or `map(...)`, as ``callee(...)``.

    ``callee`` is what the name the code wrote holds when the call runs.
    Where it is Python's own and a tracked value is the argument, pyct's
    conversion answers (`conversions.picked`); any other call is the callee's
    own, the target's function included.
    """
    conversion = conversions.picked(callee, args, kwargs)
    if conversion is not None:
        return conversion(*args, **kwargs)
    return callee(*args, **kwargs)


def method(bound: Callable[..., object], /, *args: object, **kwargs: object) -> Any:
    """A call written ``receiver.name(...)`` with a name str has, as ``bound(...)``.

    A plain str's own method given a tracked str runs as it runs on a tracked
    str holding the plain one's text (`strs.on_text`). Any other call is the
    bound method's own, whoever's it is. Only the method's type and its
    receiver's are read, and the arguments' types only on a plain str's.
    """
    text = type(bound) is types.BuiltinMethodType and type(bound.__self__) is str
    if text and any(type(arg) is ConcolicStr for arg in (*args, *kwargs.values())):
        return strs.on_text(cast(types.BuiltinMethodType, bound), *args, **kwargs)
    return bound(*args, **kwargs)


def _handed(left: object, right: object) -> bool:
    """Whether a plain number on the left hands an operator to the tracked value on the right.

    A plain float meets a tracked int, and a plain True or False a tracked
    int or bool, as the tracked value's own reflected operation, since
    Python's float and bool answer first and plainly.
    """
    if type(left) is float:
        return type(right) is ConcolicInt
    return type(left) is bool and (type(right) is ConcolicInt or type(right) is ConcolicBool)


def _operator(operation: Callable[..., object], reflected: str) -> Callable[..., Any]:
    """`left <op> right` where the code writes it, the right side's ``reflected`` first when
    a plain number on the left hands it over (see `_handed`).

    The reflected operation's NotImplemented, which it answers for what it
    does not take, leaves the operator to Python, as does any other pair.
    """

    def route(left: object, right: object, /) -> Any:
        if _handed(left, right):
            answer = getattr(type(right), reflected)(right, left)
            if answer is not NotImplemented:
                return answer
        return operation(left, right)

    return route


# each operator pyct substitutes, Python's own with the right operand's reflected method. A
# compare's is the one Python asks of the right operand, its operands swapped: `2.5 < n` is
# `n > 2.5`
add = _operator(operator.add, "__radd__")
sub = _operator(operator.sub, "__rsub__")
mul = _operator(operator.mul, "__rmul__")
truediv = _operator(operator.truediv, "__rtruediv__")
floordiv = _operator(operator.floordiv, "__rfloordiv__")
mod = _operator(operator.mod, "__rmod__")
power = _operator(operator.pow, "__rpow__")
lshift = _operator(operator.lshift, "__rlshift__")
rshift = _operator(operator.rshift, "__rrshift__")
bit_and = _operator(operator.and_, "__rand__")
bit_or = _operator(operator.or_, "__ror__")
bit_xor = _operator(operator.xor, "__rxor__")
lt = _operator(operator.lt, "__gt__")
le = _operator(operator.le, "__ge__")
gt = _operator(operator.gt, "__lt__")
ge = _operator(operator.ge, "__le__")
eq = _operator(operator.eq, "__eq__")
ne = _operator(operator.ne, "__ne__")


# the frames blame reads through: a raise under one of them, from Python's own `in` or from
# the target's own `__contains__`, is the target's
PASSING: frozenset[types.CodeType] = frozenset(
    function.__code__
    # every operator's function runs the one code `_operator` makes
    for function in (is_, is_not, in_, not_in, call, method, add)
)

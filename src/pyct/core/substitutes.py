"""What intercepted code calls: `is` and `in` where the target wrote them, and `len`, `ord`, `chr`.

`pyct.intercept` substitutes a compare the target writes with a call of one
of these functions, through a name it binds in the module, such as
``__pyct_in__``, handing over the same operands in the same order. Python
answers `is` without asking either operand, and tests the answer of `in`
for truth before the target sees it, so a tracked value would lose its
condition in both. Here a tracked value
answers as it stands for, and any other operand gets Python's own answer
and Python's own exception.

It also binds `len`, `ord` and `chr` in the module's builtins to the three
functions `BOUND` names. Python makes their answers plain, or calls no
method of the value at all; here a tracked value that core follows through
one of them gets core's tracked answer, and every other call, keywords and
any count of arguments included, is Python's own.

Each function is a router: it picks which answer to give and calls Python
or core for it, and runs none of the target's code in its own lines. So
blame reads through its frame (`PASSING`): a raise under it is the target's
unless one of core's own frames sits below.
"""

from __future__ import annotations

import inspect
import types
from collections.abc import Callable, Mapping
from typing import Any

from pyct.core import codes, strs
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


# the tracked values core follows through each bound builtin, by their exact type, and the
# function that follows them. A tracked value's `__len__` stays a downgrade, since Python's own
# `len` makes its answer plain; pyct's asks core for the tracked length instead
# Python's own three, captured as this module loads: a target that replaces one in `builtins`
# later changes what its modules find by the name (see `pyct.intercept.wrap`), not what a
# bound function a module already holds calls, as with the builtin plain Python found
_LEN, _ORD, _CHR = len, ord, chr

_FOLLOWED: Mapping[Callable[..., object], Mapping[type, Callable[[Any], object]]] = {
    _LEN: {ConcolicStr: strs.length},
    _ORD: {ConcolicStr: codes.code},
    _CHR: {ConcolicInt: codes.character},
}


def _routed(
    python: Callable[..., object], args: tuple[object, ...], kwargs: dict[str, object]
) -> object:
    """Core's answer for one tracked argument core follows through `python`, else Python's call."""
    if _LEN(args) == 1 and not kwargs:
        follow = _FOLLOWED[python].get(type(args[0]))
        if follow is not None:
            return follow(args[0])
    return python(*args, **kwargs)


def len_(*args: object, **kwargs: object) -> object:
    # `len` where pyct binds it: a tracked string's length is a tracked int, `["len", s]`. Its
    # docstring is Python's own (see `_dressed`)
    return _routed(_LEN, args, kwargs)


def ord_(*args: object, **kwargs: object) -> object:
    # `ord` where pyct binds it: a tracked string's code is a tracked int, `["ord", c]`
    return _routed(_ORD, args, kwargs)


def chr_(*args: object, **kwargs: object) -> object:
    # `chr` where pyct binds it: a tracked int's character is a tracked string, `["chr", n]`
    return _routed(_CHR, args, kwargs)


def _dressed(bound: Callable[..., object], python: Callable[..., object]) -> None:
    """Give a bound function the names, text and signature of Python's own, as target code reads
    them: `len.__name__`, `help(len)` and `inspect.signature(len)` answer as they do in plain
    Python. Its repr and its identity stay a function's."""
    for name in ("__name__", "__qualname__", "__module__", "__doc__", "__text_signature__"):
        setattr(bound, name, getattr(python, name))
    bound.__signature__ = inspect.signature(python)  # pyrefly: ignore[missing-attribute]


# each builtin pyct binds in the target's modules, by name: Python's own, which a module's
# builtins must hold for pyct's to be found under the name, and pyct's
BOUND: Mapping[str, tuple[Callable[..., object], Callable[..., object]]] = {
    "len": (_LEN, len_),
    "ord": (_ORD, ord_),
    "chr": (_CHR, chr_),
}
for _python, _bound in BOUND.values():
    _dressed(_bound, _python)

# the frames blame reads through: a raise under one of them, from Python's own `in`, `len`,
# `ord` or `chr`, or from the target's own `__contains__` or `__len__`, is the target's
PASSING: frozenset[types.CodeType] = frozenset(
    function.__code__ for function in (is_, is_not, in_, not_in, len_, ord_, chr_, _routed)
)

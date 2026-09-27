"""A tracked number on the right of a float or bool the code writes, handed Python's operator.

Python asks the left operand of an operator first. A float or a bool on
the left answers plainly when the right is a tracked int, which is an int
to it, and a bool answers so beside a tracked bool, so the tracked value is
never asked and its condition is lost: `0.5 + n`, `2.5 < n`, `True & b`.

`pyct.intercept` writes ``0.5 + n`` as ``0.5 + __pyct_handed__(n, 0.5)``,
the literal written again beside the right operand, and ``RATE + n``, with
``RATE`` bound only to a float, as ``RATE + __pyct_handed__(n, RATE)``, and Python's own `+`
runs as written. `handed` hands back the right operand itself, unless it is
a tracked int beside a float, or a tracked int or bool beside a bool: then
it hands back a stand-in no number takes, so the left side's own operation
answers NotImplemented and Python asks the stand-in's reflected method,
which asks the tracked value's own and so keeps its condition. Where the
tracked value declines too, the stand-in answers with Python's own operator
on the literal and the tracked value, which is the plain answer Python gave.

So pyct's frame is gone before Python's operator runs, and the target's own
reflected method, on anything other than a tracked value, runs under the
target's frame alone, as written. The stand-in is named after the tracked
type it holds, so an error that names the operand's type names it as
before, and it never outlives the operator.
"""

from __future__ import annotations

import operator
import types
from collections.abc import Callable
from typing import Any

from pyct.core.bools import ConcolicBool
from pyct.core.ints import ConcolicInt

# each reflected method Python asks the right operand for, with Python's own operator, which
# answers when the tracked value declines. A compare's reflected method is the swapped compare:
# `2.5 < n` asks `n.__gt__(2.5)`
_REFLECTED: dict[str, Callable[[Any, Any], object]] = {
    "__radd__": operator.add,
    "__rsub__": operator.sub,
    "__rmul__": operator.mul,
    "__rtruediv__": operator.truediv,
    "__rfloordiv__": operator.floordiv,
    "__rmod__": operator.mod,
    "__rpow__": operator.pow,
    "__rlshift__": operator.lshift,
    "__rrshift__": operator.rshift,
    "__rand__": operator.and_,
    "__ror__": operator.or_,
    "__rxor__": operator.xor,
    "__gt__": operator.lt,
    "__ge__": operator.le,
    "__lt__": operator.gt,
    "__le__": operator.ge,
    "__eq__": operator.eq,
    "__ne__": operator.ne,
}


def _reflected(name: str, python: Callable[[Any, Any], object]) -> Callable[[Any, object], object]:
    """The stand-in's reflected method: the tracked value's own, else Python's plain answer.

    It is a router, and blame reads through it (`PASSING`): it runs nothing of
    its own, and Python's operator refusing the pair raises what the written
    operator raises.
    """

    def answer(self: Any, left: object) -> object:
        value = self.value
        answered = getattr(type(value), name)(value, left)
        return python(left, value) if answered is NotImplemented else answered

    return answer


def _stand_in(tracked: type) -> type:
    """The stand-in class for one tracked type, named as that type is."""
    methods: dict[str, object] = {
        name: _reflected(name, python) for name, python in _REFLECTED.items()
    }
    methods["__slots__"] = ("value",)
    methods["__hash__"] = None
    methods["__init__"] = _held
    return type(tracked.__name__, (), methods)


def _held(self: Any, value: object) -> None:
    self.value = value


_STAND_INS: dict[type, type] = {kind: _stand_in(kind) for kind in (ConcolicInt, ConcolicBool)}


def handed(right: object, left: object, /) -> object:
    """The right operand as the operator should meet it beside this literal on the left.

    A float hands its operator to a tracked int, and a bool to a tracked int
    or bool. Any other pair gets the right operand itself. Only types are
    read, so nothing of the target's runs here.
    """
    kind, beside = type(right), type(left)
    if kind is ConcolicInt and (beside is float or beside is bool):
        return _STAND_INS[kind](right)
    if kind is ConcolicBool and beside is bool:
        return _STAND_INS[kind](right)
    return right


# the frames blame reads through: a raise under one of them, from Python's own operator on the
# literal and the tracked value, is the target's, as it is when the target's operator raises
# each stand-in method is `_reflected`'s inner `answer`, so one built here gives the code
# object every stand-in method shares
PASSING: frozenset[types.CodeType] = frozenset(
    {handed.__code__, _reflected("__radd__", operator.add).__code__}
)

"""A walk key compared by Python's own code: a dict or set lookup, `list.index`, a sort
(let-the-solver-choose-a-small-dict-s-walk-key).

A dict or a set the target builds from a walk's keys compares a key only where two hashes meet,
so a fork recorded there would hold on some inputs and not on others, and an answer that flips
it leaves the plan. Such a compare answers as it did when the walk handed out a plain copy: the
walk key's plain value meets the other side, which records only what that side records. A
compare the target writes, or pyct writes for it, runs Python's compare instruction and is a fork
as on any tracked str or int.
"""

from __future__ import annotations

import dis
import operator
import sys
import types
from collections.abc import Callable
from typing import Any

from pyct.core.values import own

# the head of a walk key's expression, `["key", A, i]`
WALK_KEY = "key"

# the instruction a compare written in Python runs; Python's own lookups call `__eq__` from C
_COMPARE_OP = dis.opmap["COMPARE_OP"]

_OPERATORS: dict[str, Callable[[object, object], object]] = {
    "__eq__": operator.eq,
    "__ne__": operator.ne,
}


def asked_by_code(name: str, compute: Callable[..., Any]) -> Callable[..., Any]:
    """A tracked value's compare named ``name``, answered plainly where Python's own code
    compares a walk key (see ``by_python``); ``compute`` answers every other compare."""
    if name not in _OPERATORS:
        return compute

    def compared(value: object, other: object) -> Any:
        # a compare the target writes reaches its type's own through ``compute``, which holds
        # the helper; Python's own lookup reaches it through ``plainly``
        if by_python(value, other, sys._getframe(1)):
            return plainly(name, value, other)
        return compute(value, other)

    return compared


def is_walk_key(value: object) -> bool:
    """Whether a value is a walk key: a tracked str or int whose expression is `["key", A, i]`."""
    held = getattr(value, "__dict__", None)
    expression = held.get("expression") if isinstance(held, dict) else None
    return isinstance(expression, list) and expression[:1] == [WALK_KEY]


def by_python(value: object, other: object, invoker: types.FrameType | None) -> bool:
    """Whether a compare of ``value`` with ``other`` is Python's own, with a walk key on either
    side: the frame that asked for it runs no compare instruction, so C code asked."""
    if invoker is None or not (is_walk_key(value) or is_walk_key(other)):
        return False
    return invoker.f_code.co_code[invoker.f_lasti] != _COMPARE_OP


def plainly(name: str, value: object, other: object) -> object:
    """The compare named ``name`` of ``value`` with ``other``, each walk key as its plain value,
    as Python makes it: a tracked value on the other side records what it records."""
    return own(_OPERATORS[name], _bare(value), _bare(other))


def _bare(value: object) -> object:
    """A walk key's plain value, an exact str or int; any other value as it is."""
    if not is_walk_key(value):
        return value
    return str.__str__(value) if isinstance(value, str) else int.__int__(value)  # pyrefly: ignore[bad-argument-type]

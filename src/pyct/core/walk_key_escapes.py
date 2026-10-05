"""A walk key that Python's own code hashes or compares (let-the-solver-choose-a-small-dict-s-
walk-key).

A dict or a set the target builds from a walk's keys hashes each one, and compares one only where
two hashes meet; a list search Python runs, a sort and `max` compare them in C. A fork recorded
there would hold on some inputs and not on others, so each walk key such code takes escapes
(``escapes.escaped``) and answers as its plain key, as a plain copy did, and a walk key that
escaped compares as its plain key from then on. A compare the target writes runs Python's
compare instruction and is a fork, as on any tracked str or int. Code that reads a str or an
int in C without calling it, `json.dumps`, `re.match`, `repr`, `bytes` or an f-string's join,
is not seen here: a walk key such code reads does not escape.
"""

from __future__ import annotations

import dis
import operator
import sys
import types
from collections.abc import Callable
from typing import Any

from pyct.core.escapes import bare_key, escaped, has_escaped, is_walk_key
from pyct.core.values import own

# the instruction a compare written in Python runs; Python's own code calls a compare from C
_COMPARE_OP = dis.opmap["COMPARE_OP"]

_OPERATORS: dict[str, Callable[[Any, Any], object]] = {
    "__lt__": operator.lt,
    "__le__": operator.le,
    "__gt__": operator.gt,
    "__ge__": operator.ge,
    "__eq__": operator.eq,
    "__ne__": operator.ne,
}


def asked_by_code(name: str, compute: Callable[..., Any]) -> Callable[..., Any]:
    """A tracked value's compare named ``name``: where Python's own code compares a walk key
    (see ``by_python``), or a walk key that escaped is compared, each walk key escapes and the
    plain keys answer; ``compute`` answers every other compare."""

    def compared(value: object, other: object) -> Any:
        # a compare the target writes reaches its type's own through ``compute``, which holds
        # the helper; Python's own reaches it through ``plainly``
        if has_escaped(value) or has_escaped(other) or by_python(value, other, sys._getframe(1)):
            return plainly(name, value, other)
        return compute(value, other)

    return compared


def hashed(base: Callable[[Any], int]) -> Callable[[Any], int]:
    """A tracked value's hash: a walk key hashed escapes, whoever hashes it, a dict or a set
    the target builds, `hash(k)` or a cache, since a hash is not a fork pyct records."""

    def hash_of(value: object) -> int:
        escaped(value)
        return own(base, value)

    return hash_of


def by_python(value: object, other: object, invoker: types.FrameType | None) -> bool:
    """Whether a compare of ``value`` with ``other`` is Python's own, with a walk key on either
    side: the frame that asked for it runs no compare instruction, so C code asked."""
    if invoker is None or not (is_walk_key(value) or is_walk_key(other)):
        return False
    return invoker.f_code.co_code[invoker.f_lasti] != _COMPARE_OP


def plainly(name: str, value: object, other: object) -> object:
    """The compare named ``name`` of ``value`` with ``other`` as Python makes it, each walk key
    escaped and as its plain value: a tracked value on the other side records what it records."""
    escaped(value)
    escaped(other)
    return own(_OPERATORS[name], bare_key(value), bare_key(other))

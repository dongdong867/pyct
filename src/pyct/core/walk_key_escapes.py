"""Where a walk key leaves what pyct records exactly (let-the-solver-choose-a-small-dict-s-walk-
key).

The solver may choose a walk key only while every operation on it is one pyct records exactly:
its dict's own lookups, and the compares, searches and conversions the target writes on it,
each a fork. Once a walk key reaches anything else, Python's own code hashes or compares it, as
a dict or a set it is stored in, a list search, a sort or `max` does, or an operation pyct has
not taught takes it, the key escapes: a fact keeps it at the key the input holds there
(``escaped``), so no ask that reaches that point chooses it, as before walk keys. A compare
Python's own code makes answers with the plain key, as a plain copy's did, and records nothing
of its own; the other side records what it records.
"""

from __future__ import annotations

import dis
import operator
import sys
import types
from collections.abc import Callable
from typing import Any

from pyct.core.branch import Expression, Fact, caller_site
from pyct.core.values import own

# the head of a walk key's expression, `["key", A, i]`
WALK_KEY = "key"

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
        if _escaped(value) or _escaped(other) or by_python(value, other, sys._getframe(1)):
            return plainly(name, value, other)
        return compute(value, other)

    return compared


def hashed(base: Callable[[Any], int]) -> Callable[[Any], int]:
    """A tracked value's hash: a walk key hashed escapes, since only Python's own code, a dict
    or a set the target builds, hashes it."""

    def hash_of(value: object) -> int:
        escaped(value)
        return own(base, value)

    return hash_of


def is_walk_key(value: object) -> bool:
    """Whether a value is a walk key: a tracked str or int whose expression is `["key", A, i]`."""
    held = getattr(value, "__dict__", None)
    expression = held.get("expression") if isinstance(held, dict) else None
    return isinstance(expression, list) and expression[:1] == [WALK_KEY]


def escaped(value: object) -> None:
    """Note that a walk key escapes, once for each key a walk hands out: the fact that it is
    the key the input holds at its pass. Any other value is left as it is."""
    if not is_walk_key(value):
        return
    held: dict[str, Any] = value.__dict__
    if held.get("escaped"):
        return
    held["escaped"] = True
    bare = _bare(value)
    written: Expression = str.__repr__(bare) if isinstance(bare, str) else int.__int__(bare)  # pyrefly: ignore[bad-argument-type]
    held["sink"].append(Fact(["==", held["expression"], written], True, caller_site()))


def _escaped(value: object) -> bool:
    """Whether a value is a walk key that escaped: it compares as its plain key from then on,
    as a plain copy did."""
    held = getattr(value, "__dict__", None)
    return isinstance(held, dict) and bool(held.get("escaped"))


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
    return own(_OPERATORS[name], _bare(value), _bare(other))


def _bare(value: object) -> object:
    """A walk key's plain value, an exact str or int; any other value as it is."""
    if not is_walk_key(value):
        return value
    return str.__str__(value) if isinstance(value, str) else int.__int__(value)  # pyrefly: ignore[bad-argument-type]

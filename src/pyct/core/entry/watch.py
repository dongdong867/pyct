"""A call in the target's package that takes a tracked value and gives back a plain one.

`pyct.intercept` writes such a call ``f(a, b)`` as
``__pyct_answer__(f(__pyct_first__(a), __pyct_given__(b)), "f")``: ``first``
notes that a call's arguments start, each later argument passes through
``given``, and ``answer`` reads the call's answer. The callee runs from the
target's own frame, with no frame of pyct's above it, and every function
here hands back what it was given.

The answer is a loss when an argument was a tracked value, no downgrade was
recorded once the last argument was in hand, which is a downgrade the call
made inside itself, and the answer is a plain int, float, bool or str, or a
list, tuple, set, frozenset or dict holding only those. The loss is a
downgrade named by the callee as the call writes it, at the call's site, in
the sink of the call's first tracked argument (run-quiet-loss-downgrade).

The calls start and answer in the order Python runs them, so the calls
whose arguments started are a stack, and each answer takes the call on top:
a call inside the first argument answers before the call around it starts.
A call that raises never answers; its entry stays below the calls that come
after it, each of which takes its own off the top, and a call of the
target's that starts clears the stack (``forget``).
"""

from __future__ import annotations

from pyct.core.entry.bases import TRACKED_CLASSES
from pyct.core.foundation import escapes
from pyct.core.foundation.branch import Downgrade, caller_site

# the types a plain answer is made of, and the containers that may hold them
_PLAIN = frozenset({int, float, bool, str})
_CONTAINERS = frozenset({list, tuple, set, frozenset})


class _Open:
    """One call whose arguments started and that has not answered: its first tracked argument,
    and how many downgrades the input had recorded when its last argument was in hand."""

    __slots__ = ("count", "tracked")

    def __init__(self, tracked: object, count: int) -> None:
        self.tracked = tracked
        self.count = count


_OPEN: list[_Open] = []


def forget() -> None:
    """Drop every call still open, as a call of the target's that starts does."""
    _OPEN.clear()


def first[Value](value: Value, /) -> Value:
    """A call's first argument: the call starts, noting the argument when it is tracked."""
    _OPEN.append(_Open(value if type(value) in TRACKED_CLASSES else None, escapes.LOST[0]))
    return value


def given[Value](value: Value, /) -> Value:
    """A later argument of the call on top, noted when it is tracked and the call has none yet."""
    top = _OPEN[-1]
    if top.tracked is None and type(value) in TRACKED_CLASSES:
        top.tracked = value
    top.count = escapes.LOST[0]
    return value


def answer[Result](result: Result, name: str, /) -> Result:
    """The call's answer, handed back, after a loss it shows is recorded under ``name``."""
    top = _OPEN.pop()
    tracked = top.tracked
    if tracked is None or escapes.LOST[0] != top.count or not _plain(result):
        return result
    site = caller_site()
    escapes.lost(tracked.sink, Downgrade(name=name, site=site), (tracked,))  # pyrefly: ignore[missing-attribute]
    return result


def _plain(value: object) -> bool:
    """Whether a value is a plain int, float, bool or str, or a container of only those."""
    stack = [value]
    while stack:
        part = stack.pop()
        kind = type(part)
        if kind in _PLAIN:
            continue
        if kind in _CONTAINERS:
            stack.extend(part)  # pyrefly: ignore[bad-argument-type]
        elif kind is dict:
            stack.extend(part.keys())  # pyrefly: ignore[missing-attribute]
            stack.extend(part.values())  # pyrefly: ignore[missing-attribute]
        else:
            return False
    return True

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
whose arguments started are a stack, one per thread, and each answer takes
the newest call its own frame started: a call inside the first argument
answers before the call around it starts. A call that raises never answers.
When the raise is caught in a frame below the call's, the call's entry is
left above that frame's own calls, and the next of them to take an argument
or answer drops it. When it is caught in the call's own frame, the entry
stays below that frame's later calls, and a stack keeps its newest
`MOST_OPEN` entries. A call of the target's that starts clears every
thread's stack (``forget``). The count of downgrades the watch reads is the
process's, on every thread (`escapes.RECORDED`).
"""

from __future__ import annotations

import sys
import threading
import types

from pyct.core.entry.bases import TRACKED_CLASSES
from pyct.core.foundation import escapes
from pyct.core.foundation.branch import Downgrade, caller_site

# the types a plain answer is made of, and the containers that may hold them
_PLAIN = frozenset({int, float, bool, str})
_CONTAINERS = frozenset({list, tuple, set, frozenset})


class _Open:
    """One call whose arguments started and that has not answered: the frame that started it,
    its first tracked argument, and how many downgrades the input had recorded when its last
    argument was in hand."""

    __slots__ = ("count", "frame", "tracked")

    def __init__(self, frame: types.FrameType, tracked: object, count: int) -> None:
        self.frame = frame
        self.tracked = tracked
        self.count = count


# the most calls one thread's stack keeps open, the newest
MOST_OPEN = 4096
# each thread's open calls, the newest last, by the thread's identity
_OPEN: dict[int, list[_Open]] = {}


def forget() -> None:
    """Drop every call still open on every thread, as a call of the target's that starts
    does."""
    _OPEN.clear()


def first[Value](value: Value, /) -> Value:
    """A call's first argument: the call starts, noting the argument when it is tracked."""
    tracked = value if type(value) in TRACKED_CLASSES else None
    calls = _OPEN.setdefault(threading.get_ident(), [])
    if len(calls) == MOST_OPEN:
        del calls[0]
    calls.append(_Open(sys._getframe(1), tracked, escapes.RECORDED[0]))
    return value


def given[Value](value: Value, /) -> Value:
    """A later argument of the frame's newest open call, noted when it is tracked and the call
    has none yet."""
    top = _top(sys._getframe(1))
    if top is None:
        return value
    if top.tracked is None and type(value) in TRACKED_CLASSES:
        top.tracked = value
    top.count = escapes.RECORDED[0]
    return value


def answer[Result](result: Result, name: str, /) -> Result:
    """The call's answer, handed back, after a loss it shows is recorded under ``name``."""
    top = _top(sys._getframe(1))
    if top is None:
        return result
    _OPEN[threading.get_ident()].pop()
    tracked = top.tracked
    if tracked is None or escapes.RECORDED[0] != top.count or not _plain(result):
        return result
    site = caller_site()
    escapes.lost(tracked.sink, Downgrade(name=name, site=site), (tracked,))  # pyrefly: ignore[missing-attribute]
    return result


def _top(frame: types.FrameType) -> _Open | None:
    """The newest call ``frame`` started, after the calls above it are dropped: each one a frame
    above this one started, whose raise was caught below it. None when ``frame`` has no call
    open, which leaves the stack as it was."""
    calls = _OPEN.get(threading.get_ident(), [])
    for at in range(len(calls) - 1, -1, -1):
        if calls[at].frame is frame:
            del calls[at + 1 :]
            return calls[at]
    return None


def _plain(value: object) -> bool:
    """Whether a value is a plain int, float, bool or str, or a container of only those, each
    container read once."""
    stack = [value]
    read: set[int] = set()
    while stack:
        part = stack.pop()
        kind = type(part)
        if kind in _PLAIN:
            continue
        if kind not in _CONTAINERS and kind is not dict:
            return False
        if id(part) in read:
            continue
        read.add(id(part))
        if kind is dict:
            stack.extend(part.keys())  # pyrefly: ignore[missing-attribute]
            stack.extend(part.values())  # pyrefly: ignore[missing-attribute]
        else:
            stack.extend(part)  # pyrefly: ignore[bad-argument-type]
    return True

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
Its entry is dropped when its frame starts a call at the same place again,
or when a call of a frame below it takes an argument or answers, once the
frame that left it has returned. A stack keeps its newest `MOST_OPEN`
entries. A call of the target's that starts drops every thread's open calls
(``forget``). The count of downgrades the watch reads is the process's, on
every thread (`escapes.RECORDED`). While the interpreter shuts down, as a
target's tracer can still run, each function hands its value back and does
nothing else: the modules it reads may be cleared by then, and the function
holds what tells it so.
"""

from __future__ import annotations

import sys
import threading
import types
from collections.abc import Callable

from pyct.core.entry.bases import TRACKED_CLASSES
from pyct.core.foundation import escapes
from pyct.core.foundation.branch import Downgrade, caller_site

# Python's own, which each watched call reads: the target may put others in `builtins` while
# one of its calls runs
_id, _len, _range, _set, _type = id, len, range, set, type

# the types a plain answer is made of, and the containers that may hold them
_PLAIN = frozenset({int, float, bool, str})
_CONTAINERS = frozenset({list, tuple, set, frozenset})


class _Open:
    """One call whose arguments started and that has not answered: the frame that started it and
    the instruction it started at, its first tracked argument, and how many downgrades the input
    had recorded when its last argument was in hand."""

    __slots__ = ("at", "count", "frame", "tracked")

    def __init__(self, frame: types.FrameType, tracked: object, count: int) -> None:
        self.frame = frame
        self.at = frame.f_lasti
        self.tracked = tracked
        self.count = count


class _Calls(threading.local):
    """One thread's open calls, the newest last, and the round of ``forget`` they belong to."""

    def __init__(self) -> None:
        self.open: list[_Open] = []
        self.round = _ROUND[0]


# the most calls one thread's stack keeps open, the newest
MOST_OPEN = 4096
# how many times the open calls were dropped, which a thread's stack from before is out of
_ROUND = [0]
_CALLS = _Calls()


def forget() -> None:
    """Drop every call still open on every thread, as a call of the target's that starts
    does."""
    _ROUND[0] += 1


def first[Value](value: Value, /, *, _ending: Callable[[], bool] = sys.is_finalizing) -> Value:
    """A call's first argument: the call starts, noting the argument when it is tracked."""
    if _ending():
        return value
    tracked = value if _type(value) in TRACKED_CLASSES else None
    calls = _calls()
    call = _Open(sys._getframe(1), tracked, escapes.RECORDED[0])
    _drop_left_at(calls, call)
    if _len(calls) == MOST_OPEN:
        del calls[0]
    calls.append(call)
    return value


def given[Value](value: Value, /, *, _ending: Callable[[], bool] = sys.is_finalizing) -> Value:
    """A later argument of the frame's newest open call, noted when it is tracked and the call
    has none yet."""
    if _ending():
        return value
    top = _top(_calls(), sys._getframe(1))
    if top is None:
        return value
    if top.tracked is None and _type(value) in TRACKED_CLASSES:
        top.tracked = value
    top.count = escapes.RECORDED[0]
    return value


def answer[Result](
    result: Result, name: str, /, *, _ending: Callable[[], bool] = sys.is_finalizing
) -> Result:
    """The call's answer, handed back, after a loss it shows is recorded under ``name``."""
    if _ending():
        return result
    calls = _calls()
    top = _top(calls, sys._getframe(1))
    if top is None:
        return result
    calls.pop()
    tracked = top.tracked
    if tracked is None or escapes.RECORDED[0] != top.count or not _plain(result):
        return result
    site = caller_site()
    escapes.lost(tracked.sink, Downgrade(name=name, site=site), (tracked,))  # pyrefly: ignore[missing-attribute]
    return result


def _calls() -> list[_Open]:
    """This thread's open calls, none from before the last ``forget``."""
    held = _CALLS
    if held.round != _ROUND[0]:
        held.open = []
        held.round = _ROUND[0]
    return held.open


def _drop_left_at(calls: list[_Open], call: _Open) -> None:
    """Drop the call the frame left open at the place ``call`` starts, and every call after it:
    the frame runs that place again, so none of them answers."""
    for at in _range(_len(calls) - 1, -1, -1):
        if calls[at].frame is not call.frame:
            return
        if calls[at].at == call.at:
            del calls[at:]
            return


def _top(calls: list[_Open], frame: types.FrameType) -> _Open | None:
    """The newest call ``frame`` started, after the calls above it are dropped: each one left
    open by a frame above that has since returned. None when ``frame`` has no call open, which
    leaves the stack as it was."""
    for at in _range(_len(calls) - 1, -1, -1):
        if calls[at].frame is frame:
            del calls[at + 1 :]
            return calls[at]
    return None


def _plain(value: object) -> bool:
    """Whether a value is a plain int, float, bool or str, or a container of only those, each
    container read once."""
    stack = [value]
    read: set[int] = _set()
    while stack:
        part = stack.pop()
        kind = _type(part)
        if kind in _PLAIN:
            continue
        if kind not in _CONTAINERS and kind is not dict:
            return False
        if _id(part) in read:
            continue
        read.add(_id(part))
        if kind is dict:
            stack.extend(part.keys())  # pyrefly: ignore[missing-attribute]
            stack.extend(part.values())  # pyrefly: ignore[missing-attribute]
        else:
            stack.extend(part)  # pyrefly: ignore[bad-argument-type]
    return True

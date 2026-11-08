"""A call in the target's package into code pyct cannot see inside, that takes a tracked value
and gives back a plain one.

`pyct.intercept` writes such a call ``f(a, b)`` as
``__pyct_answer__(__pyct_called__(f)(__pyct_given__(a), __pyct_given__(b)), "f")``:
``called`` notes that a call starts and whether pyct can see inside its
callee, each argument passes through ``given``, and ``answer`` reads the
call's answer. The callee runs from the target's own frame, with no frame of
pyct's above it, and every function here hands back what it was given.

pyct sees inside a function of the target's package, whose module runs with
the builtins pyct binds, so a call of one, reached directly or through a
bound method, a `functools.partial`, a function or `functools.lru_cache`
wrapper that holds it in its own ``__wrapped__``, as `functools.wraps`
writes it, or its class's `__call__`, is not judged: the calls and
operations inside it are, so a cached answer of `functools.lru_cache`
records nothing. Any other callee is, as one
written in C or one outside the target's package (run-quiet-loss-downgrade).
Its answer is a loss when an argument is a tracked value, or a list, tuple
or dict holding one among its first `MOST_ITEMS` items, no fork or downgrade
was recorded once the last argument was in hand, which is one the call made
inside itself, and the answer is a plain int, float, bool, str or bytes, or
a list, tuple, set, frozenset or dict holding only those. The loss is a
downgrade named by the callee as the call writes it, at the call's site, in
the sink of the call's first tracked value.

The calls start and answer in the order Python runs them, so the calls
that started and have not answered are a stack, one per thread, and each
answer takes the newest call its own frame started: a call inside an
argument starts after the call around it and answers before that call's
next argument. A call that raises never answers. Its entry is dropped, with
the entries above it, when its frame starts a call at the same place again,
or when a call of a frame below it takes an argument or answers, once the
frame that left it has returned. A stack keeps its newest `MOST_OPEN`
entries. A call of the target's that starts drops every thread's open calls
(``forget``). The count of forks and downgrades the watch reads is the
process's, on every thread (`escapes.RECORDED`). While the interpreter shuts
down, as a target's tracer can still run, each function hands its value
back and does nothing else: the modules it reads may be cleared by then, and
the function holds what tells it so.
"""

from __future__ import annotations

import functools
import itertools
import sys
import threading
import types
from collections.abc import Callable

from pyct.core.entry.bases import TRACKED_CLASSES
from pyct.core.foundation import escapes
from pyct.core.foundation.branch import Downgrade, caller_site
from pyct.core.foundation.package_builtins import binds

# Python's own, which each watched call reads: the target may put others in `builtins` while
# one of its calls runs
_getattr, _id, _len, _next, _range, _set, _type = getattr, id, len, next, range, set, type
_PARTIAL = functools.partial
_dict_get = dict.get
# the type of a `functools.lru_cache` wrapper, which holds what it wraps as a function does
_LRU_WRAPPER = functools._lru_cache_wrapper  # pyrefly: ignore[missing-attribute]
_chain, _islice = itertools.chain, itertools.islice

# the types a plain answer is made of, and the containers that may hold them
_PLAIN = frozenset({int, float, bool, str, bytes})
_CONTAINERS = frozenset({list, tuple, set, frozenset})


class _Open:
    """One call that started and has not answered: the frame that started it and the instruction
    it started at, whether its callee is judged, its first tracked value, and how many forks and
    downgrades the process had recorded when its last argument was in hand."""

    __slots__ = ("at", "count", "frame", "judged", "tracked")

    def __init__(self, frame: types.FrameType, judged: bool, count: int) -> None:
        self.frame = frame
        self.at = frame.f_lasti
        self.judged = judged
        self.tracked: object = None
        self.count = count


class _Calls(threading.local):
    """One thread's open calls, the newest last, and the round of ``forget`` they belong to."""

    def __init__(self) -> None:
        self.open: list[_Open] = []
        self.round = _ROUND[0]


# the most calls one thread's stack keeps open, the newest
MOST_OPEN = 4096
# the most items of a list, tuple or dict passed to a call that are read for a tracked value
MOST_ITEMS = 64
# the most wrappers a callee is unwrapped through to the function it calls
_MOST_WRAPPED = 8
# how many times the open calls were dropped, which a thread's stack from before is out of
_ROUND = [0]
_CALLS = _Calls()


def forget() -> None:
    """Drop every call still open on every thread, as a call of the target's that starts
    does."""
    _ROUND[0] += 1


def called[Callee](callee: Callee, /, *, _ending: Callable[[], bool] = sys.is_finalizing) -> Callee:
    """A call's callee: the call starts, noting whether its callee is judged."""
    if _ending():
        return callee
    calls = _calls()
    call = _Open(sys._getframe(1), _judged(callee), escapes.RECORDED[0])
    _drop_left_at(calls, call)
    if _len(calls) == MOST_OPEN:
        del calls[0]
    calls.append(call)
    return callee


def given[Value](value: Value, /, *, _ending: Callable[[], bool] = sys.is_finalizing) -> Value:
    """An argument of the frame's newest open call, the tracked value it is or holds noted when
    the call is judged and has none yet."""
    if _ending():
        return value
    top = _top(_calls(), sys._getframe(1))
    if top is None:
        return value
    if top.judged and top.tracked is None:
        top.tracked = _tracked_in(value)
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
    the frame runs that place again, so none of them answers. The search passes the calls of
    frames that have returned, and stops at a call of a frame below, still running."""
    below: set[int] | None = None
    for at in _range(_len(calls) - 1, -1, -1):
        frame = calls[at].frame
        if frame is call.frame:
            if calls[at].at == call.at:
                del calls[at:]
                return
            continue
        # most often the caller's own call, the one the frame runs inside
        if frame is call.frame.f_back:
            return
        if below is None:
            below = _frames_below(call.frame)
        if _id(frame) in below:
            return


def _frames_below(frame: types.FrameType) -> set[int]:
    """The frames below ``frame`` on its thread's stack, which are still running."""
    below: set[int] = _set()
    caller = frame.f_back
    while caller is not None:
        below.add(_id(caller))
        caller = caller.f_back
    return below


def _top(calls: list[_Open], frame: types.FrameType) -> _Open | None:
    """The newest call ``frame`` started, after the calls above it are dropped: each one left
    open by a frame above that has since returned. None when ``frame`` has no call open, which
    leaves the stack as it was."""
    for at in _range(_len(calls) - 1, -1, -1):
        if calls[at].frame is frame:
            del calls[at + 1 :]
            return calls[at]
    return None


def _judged(callee: object) -> bool:
    """Whether a callee is one pyct cannot see inside: anything but a function of the target's
    package, reached through a bound method, a `functools.partial`, a wrapper that holds it in
    its own ``__wrapped__`` (`_wrapped`), or an object's own `__call__`."""
    function: object = callee
    for _ in _range(_MOST_WRAPPED):
        kind = _type(function)
        if kind is types.FunctionType and binds(function.__builtins__):  # pyrefly: ignore[missing-attribute]
            return False
        if kind is types.FunctionType or kind is _LRU_WRAPPER:
            function = _wrapped(function)
        elif kind is types.MethodType:
            function = function.__func__  # pyrefly: ignore[missing-attribute]
        elif kind is _PARTIAL:
            function = function.func  # pyrefly: ignore[missing-attribute]
        else:
            function = _getattr(kind, "__call__", None)
            if _type(function) is not types.FunctionType:
                return True
        if function is None:
            return True
    return True


def _wrapped(wrapper: object) -> object:
    """What a function or a `functools.lru_cache` wrapper holds in its own ``__wrapped__``, as
    `functools.wraps`, `functools.update_wrapper` and `functools.lru_cache` write it, else
    None. Neither type can be subclassed, so its ``__dict__`` is Python's own."""
    return _dict_get(wrapper.__dict__, "__wrapped__")  # pyrefly: ignore[missing-attribute]


def _tracked_in(value: object) -> object:
    """The tracked value an argument is, or the first one a list, tuple or dict holds among its
    first `MOST_ITEMS` items, else None."""
    kind = _type(value)
    if kind in TRACKED_CLASSES:
        return value
    if kind is list or kind is tuple:
        items = _islice(value, MOST_ITEMS)  # pyrefly: ignore[no-matching-overload, bad-argument-type]
    elif kind is dict:
        items = _chain.from_iterable(_islice(value.items(), MOST_ITEMS))  # pyrefly: ignore[missing-attribute]
    else:
        return None
    return _next((item for item in items if _type(item) in TRACKED_CLASSES), None)


def _plain(value: object) -> bool:
    """Whether a value is a plain int, float, bool, str or bytes, or a container of only those,
    each container read once."""
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

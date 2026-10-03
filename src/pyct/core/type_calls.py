"""What a method of range or a dict view type answers when the target calls it through the type.

Python refuses to subclass range and its view types, so a tracked range
(`pyct.core.ranges`) and a tracked dict's views (`pyct.core.dict_views`) are
classes of pyct's that report Python's type as their class, and `type(v)`
answers Python's type in the target's package (`pyct.core.bound.type_`).
Python's own method checks its receiver's real class in C, so
`type(r).__len__(r)` would refuse a tracked range where plain Python
answers. pyct substitutes a call ``<receiver>.<name>(...)`` whose name is a
method one of these types defines (`NAMES`) and whose receiver is written
`type(x)`, `x.__class__`, or a name spelled as one of the types
(`pyct.intercept.calls`), and when the callee is Python's own method,
`pyct.core.bound` hands the call its router here (`ROUTERS`):

- a tracked value of the method's type as the receiver runs the value's own
  method of that name, so the call records what `r.__len__()` records;
- that value with a keyword, or with a count of arguments the value's own
  method does not take, gets Python's refusal in Python's words, from
  Python's method on an empty value of the type;
- any other receiver, a plain value or another tracked type among them, is
  Python's own method, its refusals included.

A method the types inherit from object takes any receiver and is not routed.
Each router picks which answer to give and runs none of the target's code in
its own lines, so blame reads through its frame (`PASSING`), and so does the
check whether a size asked is a walk's own (`pyct.core.list_reads.caller`).
"""

from __future__ import annotations

import inspect
import types
from collections.abc import Callable, Mapping
from typing import Any

from pyct.core import list_reads
from pyct.core.dict_views import ConcolicItems, ConcolicKeys, ConcolicValues
from pyct.core.ranges import ConcolicRange
from pyct.core.values import own

# a method called on a value, as each type's own methods are: not a staticmethod, such as
# `__new__`, which never takes a tracked value as its receiver
_CALLED_ON_A_VALUE = (types.WrapperDescriptorType, types.MethodDescriptorType)

# each tracked class, beside an empty plain value of the type it reports
_EMPTY: tuple[tuple[type, object], ...] = (
    (ConcolicRange, range(0)),
    (ConcolicKeys, {}.keys()),
    (ConcolicValues, {}.values()),
    (ConcolicItems, {}.items()),
)

# what a positional argument the value's own method takes is, as the call reaches it
_POSITIONAL = (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)


def _methods(kind: type) -> dict[str, Callable[..., object]]:
    """The methods a type defines that are called on a value, by name."""
    return {
        name: member
        for name, member in vars(kind).items()
        if isinstance(member, _CALLED_ON_A_VALUE)
    }


def _taken(method: Callable[..., object]) -> int | None:
    """How many arguments past the receiver the value's own method takes, or None for one that
    takes any and hands them to Python's own method, which refuses as it refuses them."""
    try:
        parameters = inspect.signature(method).parameters.values()
    except ValueError:
        return None
    if any(parameter.kind not in _POSITIONAL for parameter in parameters):
        return None
    return len(parameters) - 1


def _router(python: Callable[..., object], tracked: type, empty: object) -> Callable[..., Any]:
    """The call of Python's method ``python``: the value's own method on a tracked value of
    ``tracked``, and Python's own on anything else."""
    method = getattr(tracked, python.__name__)
    taken = _taken(method)

    def routed(*args: object, **kwargs: object) -> object:
        if not args or type(args[0]) is not tracked:
            return python(*args, **kwargs)
        if kwargs or (taken is not None and len(args) - 1 != taken):
            # refused before the method runs, so the empty value reads as the receiver would
            return own(python, empty, *args[1:], **kwargs)
        return method(*args)

    return routed


# the name of each method of range and the dict view types that a call through the type routes
NAMES: frozenset[str] = frozenset(name for _, empty in _EMPTY for name in _methods(type(empty)))

# each such method's router, by the identity of Python's own method
ROUTERS: Mapping[int, Callable[..., Any]] = {
    id(python): _router(python, tracked, empty)
    for tracked, empty in _EMPTY
    for python in _methods(type(empty)).values()
}

# the frames blame reads through: one code, which each router shares
PASSING: frozenset[types.CodeType] = frozenset(router.__code__ for router in ROUTERS.values())
# and which a walk's size reads past, so `type(r).__len__(r)` after `type(r).__iter__(r)` is
# asked by the target's code, as `r.__len__()` after `r.__iter__()` is
list_reads.CALLED_THROUGH.update(PASSING)

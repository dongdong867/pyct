"""What a call of a `math` function answers where the target writes it, given a tracked value.

`math` reads a float's double without calling any of its methods, and an
int through its `__float__` or `__index__`, so a tracked number handed to
it would lose its condition. pyct substitutes a call written with the name
of a `math` function, `math.sqrt(x)` or `sqrt(x)` (`pyct.intercept.calls`),
and when the name holds that function, `pyct.core.bound` hands the call one
of these routers (`ROUTERS`):

- `sqrt`, `fabs`, `copysign`, `isnan`, `isinf`, `isfinite`, and `isclose`
  with plain tolerances, on a tracked float or int beside plain floats or
  ints, answer Python's own result, tracked and carrying the function's
  name as its head, `["sqrt", x]`. An int reads as itself, and render
  converts it as Python does, as a float's operation reads one. `isclose`
  writes both tolerances, whether the call gave them or not;
- `sqrt` raises ValueError below zero, so it first records
  `["not", ["<", x, 0.0]]`, taken true when it does not raise;
- any other call with a tracked argument, of another function or in a form
  not encoded here, is Python's own answer on the plain values, and a
  downgrade named by the function after it, so a call that raises records
  nothing.

A call with no tracked argument is Python's own. `floor`, `ceil` and
`trunc` ask the number for its own `__floor__`, `__ceil__` and `__trunc__`,
which follow-floats teaches, so they are not routed at all.

Each router picks which answer to give and runs none of the target's code
in its own lines, so blame reads through its frame (`PASSING`).
"""

from __future__ import annotations

import math
import types
from collections.abc import Callable, Mapping
from typing import Any, cast

from pyct.core import numbers
from pyct.core.bools import ConcolicBool
from pyct.core.branch import BranchSink, Downgrade, Expression
from pyct.core.floats import ConcolicFloat
from pyct.core.ints import ConcolicInt
from pyct.core.lists import ConcolicList
from pyct.core.strs import ConcolicStr
from pyct.core.values import forked, own, plain

# each tracked value a call may be handed, and the type of the plain value Python's own call is
# handed in its place. A tracked list is handed as it is, since its plain value reads its items
_PLAIN: Mapping[type, type | None] = {
    ConcolicFloat: float,
    ConcolicInt: int,
    ConcolicBool: bool,
    ConcolicStr: str,
    ConcolicList: None,
}

# `isclose`'s tolerances, by keyword, and what Python takes when the call leaves one out
_TOLERANCES: Mapping[str, float] = {"rel_tol": 1e-09, "abs_tol": 0.0}

# a number as a followed function reads it: its expression, and the plain value Python reads
type Read = tuple[Expression, float | int]

# how a followed function answers a call with a tracked argument, or NotImplemented for a form
# it does not encode
type Follow = Callable[[tuple[object, ...], dict[str, object], BranchSink], object]


def _read(value: object) -> Read | None:
    """A number beside a tracked one: its expression and its value, or None for any other.

    A tracked float or int reads as its expression; a plain int as itself,
    and a plain float, the target's own float subclass among them, as the
    double it holds, which is all Python's `math` reads of it.
    """
    kind = type(value)
    if kind is ConcolicInt:
        whole = cast(ConcolicInt, value)
        return whole.expression, int.__index__(whole)
    if kind is ConcolicFloat:
        real = cast(ConcolicFloat, value)
        return real.expression, float.__float__(real)
    if kind is int:
        return cast(int, value), cast(int, value)
    if isinstance(value, float) and kind not in _PLAIN:
        double = float.__float__(value)
        return double, double
    return None


def _all_read(args: tuple[object, ...], count: int) -> list[Read] | None:
    """Each of ``count`` arguments read, or None when there are more or fewer, or one is not."""
    if len(args) != count:
        return None
    read: list[Read] = []
    for arg in args:
        part = _read(arg)
        if part is None:
            return None
        read.append(part)
    return read


def _not_negative(sink: BranchSink, expression: Expression, value: float | int) -> None:
    """The fork `sqrt` takes before it runs, taken true when it does not raise, NaN included."""
    forked(sink, ["not", ["<", expression, 0.0]], not value < 0.0)


def _followed(
    function: Callable[..., object],
    count: int,
    before: Callable[[BranchSink, Expression, float | int], None] | None = None,
) -> Follow:
    """A function of ``count`` numbers, followed: Python's answer, tracked, under its name.

    ``before`` records a fork on the first number before the function runs.
    """
    head = function.__name__

    def follow(args: tuple[object, ...], kwargs: dict[str, object], sink: BranchSink) -> object:
        read = None if kwargs else _all_read(args, count)
        if read is None:
            return NotImplemented
        if before is not None:
            before(sink, *read[0])
        answer = own(function, *(value for _, value in read))
        return numbers.tracked(answer, [head, *(expression for expression, _ in read)], sink)

    return follow


def _tolerance(value: object) -> bool:
    """Whether a tolerance is a plain int or float, which `isclose` reads as its double."""
    return type(value) is int or (isinstance(value, float) and type(value) not in _PLAIN)


def _double(value: Any) -> float:
    """A plain int or float as the double Python reads it as."""
    return int.__float__(value) if type(value) is int else float.__float__(value)


def _close(args: tuple[object, ...], kwargs: dict[str, object], sink: BranchSink) -> object:
    """`isclose` of two numbers with plain tolerances: a tracked bool, both tolerances written.

    Python refuses a negative tolerance before it compares, so its own call
    runs before the expression is written, and a refused call records nothing.
    """
    read = _all_read(args, 2)
    given = {**_TOLERANCES, **kwargs}
    if read is None or given.keys() != _TOLERANCES.keys():
        return NotImplemented
    if not all(_tolerance(value) for value in given.values()):
        return NotImplemented
    answer = own(math.isclose, *(value for _, value in read), **given)
    tolerances = [_double(value) for value in given.values()]
    return numbers.tracked(answer, ["isclose", *(part for part, _ in read), *tolerances], sink)


def _plain(value: object) -> object:
    """A tracked value as the plain value Python's own call is handed, any other as itself."""
    kind = _PLAIN.get(type(value))
    return value if kind is None else plain(value, kind)


def _tracked_call(
    function: Callable[..., object],
    follow: Follow | None,
    args: tuple[object, ...],
    kwargs: dict[str, object],
) -> object:
    """A call with a tracked argument: followed, or Python's answer and a downgrade after it."""
    sink: BranchSink = next(
        part.sink  # pyrefly: ignore[missing-attribute]
        for part in (*args, *kwargs.values())
        if type(part) in _PLAIN
    )
    if follow is not None:
        answer = follow(args, kwargs, sink)
        if answer is not NotImplemented:
            return answer
    plain_args = [_plain(arg) for arg in args]
    answer = own(function, *plain_args, **{key: _plain(value) for key, value in kwargs.items()})
    sink.append(Downgrade(name=function.__name__))
    return answer


def _router(function: Callable[..., object], follow: Follow | None) -> Callable[..., Any]:
    """What a call written with the function's name calls: Python's own on plain values.

    A call with no keyword, the usual one, is handed on without them, which
    costs a plain call a third less.
    """

    def route(*args: object, **kwargs: object) -> Any:
        for arg in args:
            if type(arg) in _PLAIN:
                return _tracked_call(function, follow, args, kwargs)
        if not kwargs:
            return function(*args)
        for arg in kwargs.values():
            if type(arg) in _PLAIN:
                return _tracked_call(function, follow, args, kwargs)
        return function(*args, **kwargs)

    return route


# the functions followed on a tracked number, by name
_FOLLOWED: Mapping[str, Follow] = {
    "sqrt": _followed(math.sqrt, 1, _not_negative),
    "fabs": _followed(math.fabs, 1),
    "copysign": _followed(math.copysign, 2),
    "isnan": _followed(math.isnan, 1),
    "isinf": _followed(math.isinf, 1),
    "isfinite": _followed(math.isfinite, 1),
    "isclose": _close,
}

# the functions that ask the number itself, through a method follow-floats teaches
_ASK_THE_NUMBER = frozenset({"floor", "ceil", "trunc"})

# every function of `math` a call is routed for, by name, as this Python's `math` holds them
NAMES: frozenset[str] = frozenset(
    name
    for name, member in vars(math).items()
    if callable(member) and not name.startswith("_") and name not in _ASK_THE_NUMBER
)

# what a call written with a `math` function's name calls in its place, by the function's
# identity (see `pyct.core.bound.CALLED`)
ROUTERS: Mapping[int, Callable[..., Any]] = {
    id(getattr(math, name)): _router(getattr(math, name), _FOLLOWED.get(name)) for name in NAMES
}

# the frames blame reads through: a raise under a router, from Python's own function, is the
# target's
PASSING: frozenset[types.CodeType] = frozenset(router.__code__ for router in ROUTERS.values())

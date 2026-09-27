"""What the target's package calls in place of Python's `len`, `ord`, `chr`, `int`, `float`,
`bool` and `map`: pyct's own routers, one table for all of them (`_FOLLOWED`). `CALLED` also
holds the router of each `math` function (`pyct.core.math_calls`).

`pyct.intercept` binds `len`, `ord` and `chr` in the builtins of each module
of the target's package (`BOUND`), and hands a call written `int(...)`,
`float(...)`, `bool(...)` or `map(...)` the router `CALLED` holds for the
builtin, since a type name is never bound. Python makes the answers of the
builtins plain, or calls no method of the value at all; here a tracked
value that core follows through one of them gets core's tracked answer, and
every other call, keywords and any count of arguments included, is Python's
own. `map` with a conversion first maps pyct's router for it.

Each bound function carries the name, text and signature of Python's own,
and lives in this module under that name, so pickle saves and loads it by
reference, as it does Python's: a target can hand `len` to a process pool.
Its ``__module__`` names this module, not ``builtins``. A conversion's
router lives here too, so a `map` of one pickles by reference as well.

Each is a router: it picks which answer to give and calls Python or core
for it, and runs none of the target's code in its own lines. So blame reads
through its frame (`PASSING`): a raise under it is the target's unless one
of core's own frames sits below.
"""

from __future__ import annotations

import inspect
import types
from collections.abc import Callable, Mapping
from typing import Any

from pyct.core import codes, conversions, list_reads, math_calls, strs
from pyct.core.bools import ConcolicBool
from pyct.core.floats import ConcolicFloat
from pyct.core.ints import ConcolicInt
from pyct.core.lists import ConcolicList
from pyct.core.strs import ConcolicStr

# Python's own three, captured before this module defines its own under the same names. A target
# that replaces one in `builtins` later changes what its modules find by the name (see
# `pyct.intercept.wrap`), not what a bound function a module already holds calls, as with the
# builtin plain Python found
_LEN, _ORD, _CHR = len, ord, chr

# the tracked values core follows through each builtin, by their exact type, and the function
# that follows them: the three bound in the module's builtins, and the conversions a call
# written `int(...)`, `float(...)` or `bool(...)` reaches (`pyct.core.conversions`)
_FOLLOWED: Mapping[Callable[..., object], Mapping[type, Callable[[Any], object]]] = {
    _LEN: {ConcolicStr: strs.length, ConcolicList: list_reads.length},
    _ORD: {ConcolicStr: codes.code},
    _CHR: {ConcolicInt: codes.character},
    int: {
        ConcolicInt: conversions.itself,
        ConcolicBool: conversions.int_of_bool,
        ConcolicFloat: conversions.int_of_float,
        ConcolicStr: conversions.int_of_text,
    },
    float: {
        ConcolicFloat: conversions.itself,
        ConcolicInt: conversions.float_of_int,
        ConcolicBool: conversions.float_of_int,
        ConcolicStr: conversions.float_of_text,
    },
    bool: {
        ConcolicBool: conversions.itself,
        ConcolicInt: conversions.bool_of_int,
        ConcolicFloat: conversions.bool_of_float,
        ConcolicStr: conversions.bool_of_text,
    },
}


def _routed(
    python: Callable[..., object], args: tuple[object, ...], kwargs: dict[str, object]
) -> object:
    """Core's answer for one tracked argument core follows through `python`, else Python's call."""
    if _LEN(args) == 1 and not kwargs:
        follow = _FOLLOWED[python].get(type(args[0]))
        if follow is not None:
            return follow(args[0])
    return python(*args, **kwargs)


def len(*args: object, **kwargs: object) -> object:
    # a tracked string's or list's length is a tracked int, `["len", s]`. Its docstring is
    # Python's own (see `_dressed`)
    return _routed(_LEN, args, kwargs)


def ord(*args: object, **kwargs: object) -> object:
    # a tracked string's code is a tracked int, `["ord", c]`
    return _routed(_ORD, args, kwargs)


def chr(*args: object, **kwargs: object) -> object:
    # a tracked int's character is a tracked string, `["chr", n]`
    return _routed(_CHR, args, kwargs)


# how each conversion follows each tracked type, read straight from `_FOLLOWED` so a
# conversion of a plain value costs one lookup
_INT, _FLOAT, _BOOL = _FOLLOWED[int], _FOLLOWED[float], _FOLLOWED[bool]


def int_(*args: object, **kwargs: object) -> Any:
    """Python's `int` where the code writes it, core's conversion for one tracked value.

    A tracked str in any other form, `int(s, 16)` say, is Python's answer
    and a downgrade named `int`.
    """
    if args:
        follow = _INT.get(type(args[0]))
        if follow is not None:
            if _LEN(args) == 1 and not kwargs:
                return follow(args[0])
            if type(args[0]) is ConcolicStr:
                return conversions.int_in_another_form(*args, **kwargs)  # pyrefly: ignore
    return int(*args, **kwargs)  # pyrefly: ignore[no-matching-overload]


def float_(*args: object, **kwargs: object) -> Any:
    """Python's `float` where the code writes it, core's conversion for one tracked value."""
    if _LEN(args) == 1 and not kwargs:
        follow = _FLOAT.get(type(args[0]))
        if follow is not None:
            return follow(args[0])
    return float(*args, **kwargs)  # pyrefly: ignore[bad-argument-type]


def bool_(*args: object, **kwargs: object) -> Any:
    """Python's `bool` where the code writes it, core's truth for one tracked value, untested."""
    if _LEN(args) == 1 and not kwargs:
        follow = _BOOL.get(type(args[0]))
        if follow is not None:
            return follow(args[0])
    return bool(*args, **kwargs)  # pyrefly: ignore[no-matching-overload]


# the router map hands each item to in a conversion's place, by the conversion
_CONVERTERS: Mapping[int, Callable[..., object]] = {
    id(int): int_,
    id(float): float_,
    id(bool): bool_,
}


def map_(*args: object, **kwargs: object) -> Any:
    """Python's `map` where the code writes it, with a conversion first: map of pyct's router.

    Python's own map runs it, as lazily as ever, and pickles it by reference,
    since the router is this module's. Any other call is Python's own map.
    """
    converter = _CONVERTERS.get(id(args[0])) if args else None
    if converter is None:
        return map(*args, **kwargs)  # pyrefly: ignore[no-matching-overload]
    return map(converter, *args[1:], **kwargs)  # pyrefly: ignore[no-matching-overload]


# what a call written `int(...)`, `float(...)`, `bool(...)` or `map(...)`, or a call of a
# `math` function through a name the module binds to it, calls in place of Python's own
# function, by its identity (see `pyct.core.substitutes.call`)
CALLED: Mapping[int, Callable[..., object]] = {
    **_CONVERTERS,
    id(map): map_,
    **math_calls.ROUTERS,
}


def _dressed(bound: Callable[..., object], python: Callable[..., object]) -> None:
    """Give a bound function the doc and signature of Python's own, as target code reads them:
    `len.__doc__`, `inspect.signature(len)` and the signature `help(len)` shows answer as in
    plain Python. Its name matches by its definition, while its module, its repr, its source
    and its identity stay a function's of this module."""
    for name in ("__doc__", "__text_signature__"):
        setattr(bound, name, getattr(python, name))
    bound.__signature__ = inspect.signature(python)  # pyrefly: ignore[missing-attribute]


# each builtin pyct binds in the target's modules, by name: Python's own, which a module's
# builtins must hold for pyct's to be found under the name, and pyct's
BOUND: Mapping[str, tuple[Callable[..., object], Callable[..., object]]] = {
    "len": (_LEN, len),
    "ord": (_ORD, ord),
    "chr": (_CHR, chr),
}
for _python, _bound in BOUND.values():
    _dressed(_bound, _python)

# the frames blame reads through: a raise under one of them, from Python's own `len`, `ord`,
# `chr` or a conversion, or from the target's own `__len__` or `__int__`, is the target's
PASSING: frozenset[types.CodeType] = (
    frozenset(
        function.__code__
        for function in (len, ord, chr, _routed, int_, float_, bool_, map_, conversions.itself)
    )
    | math_calls.PASSING
)

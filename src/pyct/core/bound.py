"""What a module of the target's package finds under `len`, `ord` and `chr`: pyct's own three.

`pyct.intercept` binds these names in the builtins of each module of the
target's package (`BOUND`). Python makes the answers of the builtins plain,
or calls no method of the value at all; here a tracked value that core
follows through one of them gets core's tracked answer, and every other
call, keywords and any count of arguments included, is Python's own.

Each function carries the name, text and signature of Python's own, and
lives in this module under that name, so pickle saves and loads it by
reference, as it does Python's: a target can hand `len` to a process pool.
Its ``__module__`` names this module, not ``builtins``.

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

from pyct.core import codes, strs
from pyct.core.ints import ConcolicInt
from pyct.core.strs import ConcolicStr

# Python's own three, captured before this module defines its own under the same names. A target
# that replaces one in `builtins` later changes what its modules find by the name (see
# `pyct.intercept.wrap`), not what a bound function a module already holds calls, as with the
# builtin plain Python found
_LEN, _ORD, _CHR = len, ord, chr

_FOLLOWED: Mapping[Callable[..., object], Mapping[type, Callable[[Any], object]]] = {
    _LEN: {ConcolicStr: strs.length},
    _ORD: {ConcolicStr: codes.code},
    _CHR: {ConcolicInt: codes.character},
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
    # a tracked string's length is a tracked int, `["len", s]`. Its docstring is Python's own
    # (see `_dressed`)
    return _routed(_LEN, args, kwargs)


def ord(*args: object, **kwargs: object) -> object:
    # a tracked string's code is a tracked int, `["ord", c]`
    return _routed(_ORD, args, kwargs)


def chr(*args: object, **kwargs: object) -> object:
    # a tracked int's character is a tracked string, `["chr", n]`
    return _routed(_CHR, args, kwargs)


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

# the frames blame reads through: a raise under one of them, from Python's own `len`, `ord` or
# `chr`, or from the target's own `__len__`, is the target's
PASSING: frozenset[types.CodeType] = frozenset(
    function.__code__ for function in (len, ord, chr, _routed)
)

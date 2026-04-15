"""Runtime dispatch helpers for AST-rewritten ``int()``, ``str()``, and ``is``.

The AST transformer in ``pyct.engine.ast_transformer`` rewrites target
source so ``int(x)``, ``str(x)``, and ``x is y`` dispatch through these
helpers at execution time. Each helper preserves symbolic tracking when
given a ``Concolic`` value and falls through to the saved primitive
builtin when given a plain value.

We capture the primitive ``int``/``str`` references at module import
time (before anything can monkey-patch them) so the fall-through path
cannot recurse through the rewrites.
"""

from __future__ import annotations

from typing import Any

from pyct.core import Concolic
from pyct.utils.concolic_converter import unwrap_concolic

_ORIG_INT = int
_ORIG_STR = str


def _int(obj: Any) -> Any:
    """Dispatch ``int(obj)`` through the concolic path when applicable.

    For ``Concolic`` values, routes to ``obj.to_int()`` which returns a
    new concolic int carrying the symbolic expression. For plain values,
    falls through to the saved primitive ``int`` constructor.
    """
    if isinstance(obj, Concolic):
        to_int = getattr(obj, "to_int", None)
        if to_int is not None:
            return to_int()
    return _ORIG_INT(obj)


def _str(obj: Any) -> Any:
    """Dispatch ``str(obj)`` through the concolic path when applicable.

    Mirrors ``_int`` — routes to ``obj.to_str()`` for concolic values,
    falls through to the primitive ``str`` constructor otherwise.
    """
    if isinstance(obj, Concolic):
        to_str = getattr(obj, "to_str", None)
        if to_str is not None:
            return to_str()
    return _ORIG_STR(obj)


def _is(left: Any, right: Any) -> bool:
    """Evaluate ``left is right`` after unwrapping concolic wrappers.

    Python's ``is`` is an identity check on the object reference. For
    concolic values we compare the unwrapped primitives — two wrappers
    over the same primitive literal should test as identical.
    """
    return unwrap_concolic(left) is unwrap_concolic(right)

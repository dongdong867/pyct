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

import contextlib
import logging
from typing import Any

from pyct.core import Concolic
from pyct.utils.concolic_converter import unwrap_concolic

log = logging.getLogger("ct.core.builtin_wrappers")

_ORIG_INT = int
_ORIG_STR = str


def _int(obj: Any) -> Any:
    """Dispatch ``int(obj)`` through the concolic path when applicable.

    For ``Concolic`` values, routes to ``obj.to_int()`` which returns a
    new concolic int carrying the symbolic expression. For plain values,
    falls through to the saved primitive ``int`` constructor.

    A ``Concolic`` instance that lacks ``to_int`` logs a WARNING before
    falling through — the whole point of this module is to stop silent
    symbolic drops, so a missing helper on a subclass is an engine-author
    bug that must be visible.
    """
    if isinstance(obj, Concolic):
        to_int = getattr(obj, "to_int", None)
        if to_int is not None:
            return to_int()
        log.warning("Concolic %s missing to_int; symbolic expression dropped", type(obj).__name__)
    return _ORIG_INT(obj)


def _str(obj: Any) -> Any:
    """Dispatch ``str(obj)`` through the concolic path when applicable.

    Mirrors ``_int`` — routes to ``obj.to_str()`` for concolic values,
    falls through to the primitive ``str`` constructor otherwise. A
    missing ``to_str`` on a ``Concolic`` subclass logs a WARNING to
    prevent silent symbolic drops.
    """
    if isinstance(obj, Concolic):
        to_str = getattr(obj, "to_str", None)
        if to_str is not None:
            return to_str()
        log.warning("Concolic %s missing to_str; symbolic expression dropped", type(obj).__name__)
    return _ORIG_STR(obj)


# Side-channel registry the membership rewriter populates after
# ``_shift_line_numbers`` so the runtime concolic ``__eq__`` can map a
# Compare's source position back to its chain ID. Python's ``compile()``
# strips arbitrary AST attributes from the produced bytecode, leaving
# this position-keyed lookup as the only viable channel; the unit-test
# contract requires Compare comparators to remain plain ``Constant``
# nodes whose ``value`` is the original literal, so a Call-wrapped or
# tagged-primitive comparator path is unavailable.
_CHAIN_POSITION_REGISTRY: dict[tuple[str, int, int], int] = {}


def register_chain_position(filename: str, lineno: int, col_offset: int, chain_id: int) -> None:
    """Record a Compare's position → chain_id for runtime lookup."""
    _CHAIN_POSITION_REGISTRY[(filename, lineno, col_offset)] = chain_id


def lookup_chain_id_for_caller() -> int | None:
    """Return the chain ID of the Compare currently driving the caller's frame.

    Walks one frame up from the concolic ``__eq__`` site, reads the
    Compare's source position via ``co_positions()[f_lasti // 2]``,
    and returns the registered chain ID for that position. Returns
    None when no Compare position matches — the equality is then
    treated as non-chain by the engine scheduler.
    """
    import sys

    frame = sys._getframe(2)  # one for this helper, one for the eq()
    code = frame.f_code
    try:
        positions = list(code.co_positions())
    except AttributeError:
        return None
    instr_idx = frame.f_lasti // 2
    if not (0 <= instr_idx < len(positions)):
        return None
    start_line, _end_line, start_col, _end_col = positions[instr_idx]
    if start_line is None or start_col is None:
        return None
    return _CHAIN_POSITION_REGISTRY.get((code.co_filename, start_line, start_col))


def _compare_with_chain(left: Any, right: Any, chain_id: int) -> Any:
    """Evaluate ``left == right`` and stamp the chain ID onto the result.

    Standalone helper exposed for direct callers (the AST rewriter
    propagates chain IDs through the position registry instead). The
    helper stamps the result so primitives that do not carry the
    attribute themselves still flow the chain ID downstream.
    """
    result = left == right
    with contextlib.suppress(AttributeError, TypeError):
        result._pyct_or_chain_id = chain_id
    return result


def _is(left: Any, right: Any) -> bool:
    """Evaluate ``left is right`` with concolic-aware unwrapping.

    Python's ``is`` is an identity check on the object reference. For
    the sentinel idioms the AST transformer rewrites (``x is None``,
    ``x is True``, ``x is False``, ``x is ...``), we unwrap the concolic
    side and compare against the sentinel — this correctly models the
    author's intent, since the sentinel identity is stable.

    When NEITHER operand is concolic, we fall through to Python's
    native ``is`` so genuine object-identity checks (distinct lists,
    dicts, custom objects) retain their original semantics. The
    ``ConcolicCompareRewriter`` already restricts rewrites to literal
    comparators, so this fall-through path is rare in practice but
    guarantees correctness if the rewriter misses a case.
    """
    left_is_concolic = isinstance(left, Concolic)
    right_is_concolic = isinstance(right, Concolic)
    if not left_is_concolic and not right_is_concolic:
        return left is right
    return unwrap_concolic(left) is unwrap_concolic(right)

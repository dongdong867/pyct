"""The sense of the fork pyct records at each membership and identity test, by its site.

pyct folds every `not` over a compare with one `in`, `not in`, `is` or `is
not` into the compare, and the fork it records reads the operator it folds
to: ``not x in c`` records `x not in c`. CPython folds the same `not`
through 3.13; from 3.14 a test of ``not x in c`` reads `in` and jumps the
other way. An `is` or `is not` with True or False on one side records the
other side's own truth, the operand of ``x is not True`` taken or not. So the
value a compiled test jumps on is the recorded fork's, or its negation, and
the flow reads each side in the fork's sense.
"""

from __future__ import annotations

import ast
from collections.abc import Callable, Mapping

from pyct.results.graphs import Pace

# a site, as a fork records it: its line and column
type At = tuple[int, int]
# what a flow asks, once and only when it needs them, for the negated sites (`negated_sites`)
type Asked = Callable[[Pace], Mapping[At, bool]]

# what parsing takes a byte of source, in seconds: about 2e-7 on 3.12 and 3.13 and 1.3e-7 on 3.14,
# measured on a megabyte of `if` tests on an Apple M-series; four times the slowest
_A_BYTE = 8e-7

_MEMBERSHIP = (ast.In, ast.NotIn)
_IDENTITY = (ast.Is, ast.IsNot)


def negated_sites(source: str, pace: Pace) -> dict[At, bool]:
    """Each membership or identity test's site, and whether its recorded fork is negated.

    Negated means a true fork there is a false `in`, or a false `is`: the
    fork of ``x not in c``, or of ``x is False``, which records ``x``. A
    compiled test reads `in` or `is` through `CONTAINS_OP` or `IS_OP`, whose
    argument 1 is the negated one, so a flow swaps the sides where the two
    differ. Parsing is work no step can break into, so the pace is asked
    first whether it fits; the walk steps once a node.
    """
    pace.afford(len(source) * _A_BYTE)
    found: dict[At, bool] = {}
    # each node, and how many `not` stand directly over it
    pending: list[tuple[ast.AST, int]] = [(ast.parse(source), 0)]
    while pending:
        pace.step()
        node, nots = pending.pop()
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            pending.append((node.operand, nots + 1))
            continue
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            negated = _recorded_negated(node, nots)
            if negated is not None:
                found[(node.lineno, node.col_offset)] = negated
        pending.extend((child, 0) for child in ast.iter_child_nodes(node))
    return found


def none_negated(_pace: Pace) -> dict[At, bool]:
    """No site: every test's sides read as the value it jumps on."""
    return {}


def _recorded_negated(compare: ast.Compare, nots: int) -> bool | None:
    """Whether the compare's recorded fork is negated, or None where pyct records no fork of
    the compare's own in a known sense."""
    operator = compare.ops[0]
    if isinstance(operator, _MEMBERSHIP):
        return isinstance(operator, ast.NotIn) != (nots % 2 == 1)
    if not isinstance(operator, _IDENTITY):
        return None
    sides = [compare.left, compare.comparators[0]]
    flags = [side.value for side in sides if isinstance(side, ast.Constant) and _is_bool(side)]
    others = [side for side in sides if isinstance(side, ast.Constant) and not _is_bool(side)]
    if len(flags) != 1 or others:
        return None
    # the fork is the other side's truth: `x is True` holds when it does, `x is False` when not
    return flags[0] is False


def _is_bool(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and (node.value is True or node.value is False)

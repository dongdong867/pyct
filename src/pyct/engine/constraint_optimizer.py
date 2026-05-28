"""SMT constraint rewrite layer.

Sits between the engine's constraint pool and the solver. Walks each
constraint's leaf predicate looking for known solver-hostile emission
shapes and substitutes friendlier forms in place.

Current rules:

- ``s.count(sub) == k`` with literal ``sub`` and literal ``k`` is
  emitted by ``core/str/queries.py:_build_count_expression`` as an
  ITE around a ``(div (- len (len (str.replace_all region sub "")))
  (len sub))`` tree. ``str.replace_all`` inside a length term forces
  cvc5 to enumerate; cvc5 typically returns UNKNOWN on these. The
  optimizer collapses the predicate into:

  - ``k == 0``        →  ``(not (str.contains region sub))``
  - ``k >= 1`` literal →  k-fold chained ``str.indexof`` form

  Symbolic ``sub`` cannot be collapsed safely (the indexof chain would
  embed the symbolic sub at multiple depths and the contains-collapse
  is unsound), so the rule preserves the original ITE and bumps a
  separate skip counter for telemetry. Literal empty ``sub`` is a
  no-op: the original ITE's empty-sub arm (``len + 1``) already
  carries Python's ``s.count("") == len(s) + 1`` semantics, and the
  contains-collapse would silently change that.

- ``s.lower() == "literal"`` / ``s.upper() == "literal"`` with an
  ASCII compared literal is emitted by
  ``core/str/helpers.py:CaseConverter`` as a 26-deep ``str.replace_all``
  chain over ``s``. The optimizer collapses the predicate into a
  char-wise length+equality form:
  ``(and (= (str.len s) N)
         (or (= (str.at s 0) <lo>) (= (str.at s 0) <hi>))
         …)``
  which the solver can drive by direct character assignment instead of
  enumerating 26 nested replacements. Non-ASCII compared literals fall
  back to the baseline chain.

Counters live on ``ExplorationState`` so the engine can attribute fire
vs. skip rates on the result without the optimizer reaching across
modules for telemetry plumbing.
"""

from __future__ import annotations

from typing import Any

from pyct.core import Concolic
from pyct.engine.state import ExplorationState
from pyct.utils.smt_converter import py2smt

_NEG_ONE_SMT = py2smt(-1)


def optimize(constraint: Any, state: ExplorationState | None) -> Any:
    """Rewrite ``constraint``'s leaf predicate in place when a rule fires.

    Returns the same ``Constraint`` instance; the predicate's ``expr``
    is replaced when a substitution applies. State counters are bumped
    only when ``state`` is non-None — callers outside the engine loop
    can pass ``None`` to run the rewrite without telemetry side-effects.

    Tolerates non-Constraint inputs (e.g., raw SMT strings used by tests
    that drive ``_solve`` directly): returns them unchanged. The engine's
    real constraints_to_solve always carries ``Constraint`` instances.
    """
    predicate = getattr(constraint, "predicate", None)
    if predicate is None:
        return constraint

    rewritten = _rewrite_node(predicate.expr, state)
    if rewritten is not None:
        predicate.expr = rewritten
    return constraint


def _rewrite_node(expr: Any, state: ExplorationState | None) -> Any | None:
    """Attempt to rewrite ``expr``. Return new expr or ``None`` if unchanged.

    Handles the count-equality at the root, plus one level of ``(not …)``
    wrap. Deeper recursion is intentionally avoided — the current rules
    target top-level predicates only.
    """
    if not isinstance(expr, list) or not expr:
        return None

    head = expr[0]
    if head == "not" and len(expr) == 2:
        inner = _rewrite_node(expr[1], state)
        if inner is None:
            return None
        return ["not", inner]
    if head == "=" and len(expr) == 3:
        rewritten = _rewrite_count_equality(expr[1], expr[2], state)
        if rewritten is not None:
            return rewritten
        return _rewrite_case_fold_equality(expr[1], expr[2], state)
    return None


def _peel_concolic(node: Any) -> Any:
    """Unwrap a Concolic instance to its underlying symbolic expression."""
    if isinstance(node, Concolic):
        return _peel_concolic(node.expr)
    return node


def _rewrite_count_equality(
    lhs: Any,
    rhs: Any,
    state: ExplorationState | None,
) -> Any | None:
    """Try to collapse ``(= <count_expr> <k>)`` into a friendlier form."""
    parts = _extract_count_parts(_peel_concolic(lhs))
    if parts is None:
        return None
    region_node, sub_node = parts

    k = _literal_int(_peel_concolic(rhs))
    if k is None:
        return None

    sub_kind, sub_smt = _classify_sub(sub_node)
    if sub_kind == "symbolic":
        if state is not None:
            state.gen_count_skipped_symbolic_sub += 1
        return None
    if sub_kind == "literal-empty":
        # Original ITE's empty-sub arm already encodes len + 1. A
        # contains-collapse would silently change Python semantics, so
        # leave the predicate intact and don't bump either counter.
        return None

    rewritten = _build_count_rewrite(region_node, sub_smt, k)
    if state is not None:
        state.gen_count_rewritten += 1
    return rewritten


def _extract_count_parts(node: Any) -> tuple[Any, Any] | None:
    """Return ``(region, sub)`` if ``node`` matches the count-ITE shape.

    Matches the AST that ``core/str/queries.py:_build_count_expression``
    emits — an ``ite`` whose else-branch is the
    ``(div (- len (len (str.replace_all region sub ""))) (len sub))``
    tree.  Returns ``None`` on any structural mismatch.
    """
    if not (isinstance(node, list) and len(node) == 4 and node[0] == "ite"):
        return None

    else_branch = node[3]
    if not (isinstance(else_branch, list) and len(else_branch) == 3 and else_branch[0] == "div"):
        return None

    diff = else_branch[1]
    if not (isinstance(diff, list) and len(diff) == 3 and diff[0] == "-"):
        return None

    replace_term = diff[2]
    if not (
        isinstance(replace_term, list)
        and len(replace_term) == 2
        and replace_term[0] == "str.len"
    ):
        return None
    replace_call = replace_term[1]
    if not (
        isinstance(replace_call, list)
        and len(replace_call) == 4
        and replace_call[0] == "str.replace_all"
    ):
        return None

    return replace_call[1], replace_call[2]


def _classify_sub(node: Any) -> tuple[str, Any]:
    """Classify the sub slot. Returns ``(kind, sub_smt)``.

    ``kind`` is one of ``"literal-empty"``, ``"literal-nonempty"``,
    ``"symbolic"``. ``sub_smt`` is the SMT-string form to splice into a
    rewritten predicate (only meaningful for the literal kinds).

    A literal sub arrives as a py2smt-quoted string (e.g., ``'"abc"'``);
    a symbolic sub arrives as a bare variable name (e.g., ``"sub_VAR"``)
    or a nested expression list. Concolic wrappers are peeled first.
    """
    if isinstance(node, Concolic):
        return _classify_sub(node.expr)
    if isinstance(node, str) and _is_quoted_smt_string(node):
        return ("literal-empty", node) if node == '""' else ("literal-nonempty", node)
    return "symbolic", node


def _is_quoted_smt_string(node: str) -> bool:
    """Return True if ``node`` is an SMT-quoted string literal."""
    return len(node) >= 2 and node.startswith('"') and node.endswith('"')


def _literal_int(node: Any) -> int | None:
    """Return the Python int if ``node`` is an SMT integer literal."""
    if not isinstance(node, str):
        return None
    if node.isdigit():
        return int(node)
    return None


def _build_count_rewrite(region: Any, sub_smt: Any, k: int) -> Any:
    """Build the rewritten predicate for ``count(region, sub) == k``."""
    if k == 0:
        return ["not", ["str.contains", region, sub_smt]]
    return _build_indexof_chain(region, sub_smt, k)


def _build_indexof_chain(region: Any, sub_smt: Any, k: int) -> Any:
    """Build a k-fold chained ``str.indexof`` form asserting exactly ``k`` matches.

    Each match is located by re-anchoring the indexof start to the
    previous match's position plus ``str.len sub``. The (k+1)-th
    indexof call must return ``-1`` to lock "exactly k" (not just "at
    least k").
    """
    offset: Any = "0"
    positions: list[Any] = []
    for _ in range(k):
        indexof = ["str.indexof", region, sub_smt, offset]
        positions.append(indexof)
        offset = ["+", indexof, ["str.len", sub_smt]]

    terminator = ["=", ["str.indexof", region, sub_smt, offset], _NEG_ONE_SMT]
    clauses: list[Any] = [[">=", pos, "0"] for pos in positions]
    clauses.append(terminator)
    return _nest_and(clauses)


def _nest_and(clauses: list[Any]) -> Any:
    """Right-nest a list of clauses into binary ``and`` calls.

    A flat ``(and a b c)`` is equally valid SMT, but right-nesting
    matches the dispatch's example shape and keeps each ``and`` node
    binary for any downstream walker that assumes that arity.
    """
    if len(clauses) == 1:
        return clauses[0]
    return ["and", clauses[0], _nest_and(clauses[1:])]


# ---------------------------------------------------------------------------
# Case-fold equality rewrite (s.lower() == "literal" / s.upper() == "literal")
# ---------------------------------------------------------------------------

_LOWER_PAIRS_OUTER_FIRST: list[tuple[str, str]] = [
    (chr(90 - i), chr(122 - i)) for i in range(26)
]
_UPPER_PAIRS_OUTER_FIRST: list[tuple[str, str]] = [
    (chr(122 - i), chr(90 - i)) for i in range(26)
]


def _rewrite_case_fold_equality(
    lhs: Any,
    rhs: Any,
    state: ExplorationState | None,
) -> Any | None:
    """Try to collapse ``(= <case_fold_chain> "<literal>")`` into a charwise form.

    Detects the 26-deep ``str.replace_all`` chain that ``CaseConverter``
    emits for ``s.lower()`` / ``s.upper()`` and, when the compared
    literal is ASCII-only, substitutes a length+per-char-OR form. Non-
    ASCII compared literals leave the predicate unchanged (the skip
    counter is owned by the non-ASCII fallback rule).
    """
    base_node = _extract_case_fold_base(_peel_concolic(lhs))
    if base_node is None:
        return None

    literal = _extract_smt_string_literal(_peel_concolic(rhs))
    if literal is None or not _is_ascii(literal):
        return None

    rewritten = _build_case_fold_rewrite(base_node, literal)
    if state is not None:
        state.gen_case_fold_rewritten += 1
    return rewritten


def _extract_case_fold_base(node: Any) -> Any | None:
    """If ``node`` is a 26-deep replace_all chain matching ``to_lower`` or
    ``to_upper`` emission, return the inner base expression. Otherwise return
    ``None``.

    Walks outer-first, collecting ``(from, to)`` char pairs at each
    ``str.replace_all`` level, then matches against the expected
    descending-letter sequence either ``(Z,z)…(A,a)`` (to_lower) or
    ``(z,Z)…(a,A)`` (to_upper).
    """
    pairs: list[tuple[str, str]] = []
    current: Any = node
    while (
        isinstance(current, list)
        and len(current) == 4
        and current[0] == "str.replace_all"
    ):
        from_char = _strip_smt_string(current[2])
        to_char = _strip_smt_string(current[3])
        if from_char is None or to_char is None:
            return None
        if len(from_char) != 1 or len(to_char) != 1:
            return None
        pairs.append((from_char, to_char))
        current = current[1]

    if len(pairs) != 26:
        return None
    if pairs != _LOWER_PAIRS_OUTER_FIRST and pairs != _UPPER_PAIRS_OUTER_FIRST:
        return None
    return current


def _strip_smt_string(node: Any) -> str | None:
    """Return the inner string of an SMT-quoted string literal, or ``None``."""
    if not isinstance(node, str) or not _is_quoted_smt_string(node):
        return None
    return node[1:-1]


def _extract_smt_string_literal(node: Any) -> str | None:
    """Return the inner string of an SMT-quoted literal node, or ``None``."""
    return _strip_smt_string(node)


def _is_ascii(text: str) -> bool:
    """Return ``True`` if every character in ``text`` is ASCII (codepoint < 128)."""
    return all(ord(ch) < 128 for ch in text)


def _build_case_fold_rewrite(base: Any, literal: str) -> Any:
    """Build the charwise rewrite for ``(= <case_fold_chain> "<literal>")``.

    Emits ``(and (= (str.len base) N) <per-char-clause>…)`` where each
    per-char clause is ``(or (= (str.at base i) "<lo>") (= (str.at base
    i) "<hi>"))`` for ASCII letters and ``(= (str.at base i) "<c>")``
    for ASCII non-letters.
    """
    length_clause: Any = ["=", ["str.len", base], str(len(literal))]
    clauses: list[Any] = [length_clause]
    for index, char in enumerate(literal):
        position = ["str.at", base, str(index)]
        clauses.append(_char_clause(position, char))
    return _nest_and(clauses)


def _char_clause(position: Any, char: str) -> Any:
    """Build the per-position clause for ``char`` (case-fold OR or literal eq)."""
    if char.isalpha():
        lower = py2smt(char.lower())
        upper = py2smt(char.upper())
        return ["or", ["=", position, lower], ["=", position, upper]]
    return ["=", position, py2smt(char)]

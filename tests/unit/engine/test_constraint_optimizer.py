"""Unit tests for the constraint-optimizer SMT rewrite layer.

These tests cover the count-pattern rewrite rule landing under
``engine/constraint_optimizer.py``. The optimizer sits between path-
constraint collection and SMT-LIB emission as a pure function
``optimize(constraint, state) -> constraint``: it scans the
constraint's path predicates for known-bad emission shapes (initially:
``s.count(sub)`` encoded as a ``str.replace_all + str.len + div`` tree),
substitutes a solver-friendlier form when the rule applies, and
mutates ``state`` counters for telemetry attribution.

The current ``s.count(sub)`` emission (see
``core/str/queries.py:_build_count_expression``) produces::

    (ite (<= (str.len sub) 0)
         (+ 1 (str.len region))
         (div (- (str.len region)
                 (str.len (str.replace_all region sub "")))
              (str.len sub)))

That shape is solver-hostile — `str.replace_all` inside a length term
forces cvc5 to enumerate. The optimizer rewrites the common compared-
against-literal-int form (``count(sub) == k``) into:

- ``k == 0``           → ``(not (str.contains region sub))``
- ``k >= 1`` (concrete) → ``k``-fold chained ``str.indexof`` form
- symbolic ``sub``     → leave the original shape, bump the skip counter
- literal ``sub == ""``→ leave the original ITE so the empty-sub arm
  (``len + 1``) survives — substituting ``str.contains`` here would
  silently change semantics (Python's ``"abc".count("") == 4``,
  ``"abc" not in ""`` does not).

Tests assert on the AST shape of the constraint's path predicates
because the rewrite is structural — behavioural verification is the
acceptance-suite's job, not these unit fixtures.
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest

from pyct.engine.engine import Engine
from pyct.engine.state import ExplorationState
from pyct.predicate import Predicate
from pyct.utils.constraint import Constraint
from pyct.utils.smt_converter import py2smt

# ---------------------------------------------------------------------------
# Helpers — build the count-emission AST shape that the optimizer must see
# ---------------------------------------------------------------------------


def _count_expr(region: str, sub: Any) -> list:
    """Build the current ``s.count(sub)`` SMT emission shape.

    Mirrors ``core/str/queries.py:_build_count_expression`` so tests
    feed the optimizer the same tree the engine would emit at runtime.

    ``sub`` is spliced as-is — callers control whether it's a
    py2smt-quoted literal (e.g., ``'"abc"'``) or a bare symbolic-var
    name (e.g., ``"sub_VAR"``). The engine produces the former for
    concrete literals and the latter for symbolic inputs.
    """
    return [
        "ite",
        ["<=", ["str.len", sub], "0"],
        ["+", "1", ["str.len", region]],
        [
            "div",
            [
                "-",
                ["str.len", region],
                ["str.len", ["str.replace_all", region, sub, py2smt("")]],
            ],
            ["str.len", sub],
        ],
    ]


def _eq_count_constraint(region: str, sub: Any, k: int) -> Constraint:
    """Wrap a count-equality predicate in a fresh path Constraint."""
    expr = ["=", _count_expr(region, sub), str(k)]
    root = Constraint(parent_id=None, predicate=None)
    return root.add_child(Predicate(expr, True))


def _expr_contains(node, fragment) -> bool:
    """Recursive walk: does ``node`` contain ``fragment`` as a sub-tree?"""
    if node == fragment:
        return True
    if isinstance(node, list):
        return any(_expr_contains(child, fragment) for child in node)
    return False


def _expr_contains_op(node, op: str) -> bool:
    """Recursive walk: does ``node`` contain a list whose head is ``op``?"""
    if isinstance(node, list) and node and node[0] == op:
        return True
    if isinstance(node, list):
        return any(_expr_contains_op(child, op) for child in node)
    return False


def _rewritten_expr(constraint: Constraint):
    """Return the (possibly-rewritten) expr from the constraint's leaf predicate."""
    predicates = constraint.get_path_predicates()
    assert predicates, "optimizer must preserve at least one path predicate"
    return predicates[-1].expr


# ---------------------------------------------------------------------------
# Test 1 — engine wires the optimizer into the _solve call site
# ---------------------------------------------------------------------------


class TestOptimizerWiredIntoEngine:
    """engine.py:_solve must invoke ``optimize`` before formula-building."""

    def test_constraint_optimizer_module_exists(self):
        """The module the green-step names must be importable.

        Red: the module is absent, so ``import`` raises ``ModuleNotFoundError``.
        """
        try:
            import pyct.engine.constraint_optimizer  # noqa: F401
        except ModuleNotFoundError as e:
            pytest.fail(
                "expected pyct.engine.constraint_optimizer to exist as a module "
                f"exporting `optimize`; got {type(e).__name__}: {e}"
            )

    def test_engine_solve_calls_optimize(self):
        """``Engine._solve`` source must reference an ``optimize(`` call.

        Static introspection on the method source — pre-implementation
        no call site exists, so the substring is absent and the test
        fails. Post-green the implementer threads the rewrite through
        ``_solve`` once per constraint.
        """
        source = inspect.getsource(Engine._solve)
        assert "optimize(" in source, (
            "expected Engine._solve to call optimize(constraint, state) before "
            "the solver invocation; constraint optimization is not wired in.\n"
            f"current source:\n{source}"
        )


# ---------------------------------------------------------------------------
# Test 2 — count(sub) == 0 rewrites to (not (str.contains region sub))
# ---------------------------------------------------------------------------


class TestCountZeroSubstitutesContains:
    """``count(sub) == 0`` collapses to a contains-negation."""

    def test_count_equals_zero_rewrites_to_not_contains(self):
        from pyct.engine import constraint_optimizer

        state = ExplorationState()
        constraint = _eq_count_constraint("region_VAR", py2smt("abc"), 0)

        rewritten = constraint_optimizer.optimize(constraint, state)
        expr = _rewritten_expr(rewritten)

        # Post-green the predicate's expr is exactly
        #   (not (str.contains region_VAR "abc"))
        # No `str.replace_all` / `div` survives anywhere in the tree.
        assert not _expr_contains_op(expr, "str.replace_all"), (
            "expected rewrite to drop the str.replace_all+div form; "
            f"still present in {expr!r}"
        )
        assert not _expr_contains_op(expr, "div"), (
            f"expected rewrite to drop the div node; still present in {expr!r}"
        )
        assert _expr_contains_op(expr, "str.contains"), (
            f"expected rewritten expr to use str.contains; got {expr!r}"
        )
        assert _expr_contains_op(expr, "not"), (
            f"expected rewrite to negate the contains; got {expr!r}"
        )


# ---------------------------------------------------------------------------
# Test 3 — count(sub) == k (k > 0) rewrites to chained str.indexof
# ---------------------------------------------------------------------------


class TestCountKSubstitutesChainedIndexof:
    """``count(sub) == k`` (k > 0) collapses to a k-fold ``str.indexof`` chain."""

    def test_count_equals_two_rewrites_to_chained_indexof(self):
        from pyct.engine import constraint_optimizer

        state = ExplorationState()
        constraint = _eq_count_constraint("region_VAR", py2smt("abc"), 2)

        rewritten = constraint_optimizer.optimize(constraint, state)
        expr = _rewritten_expr(rewritten)

        # Post-green the predicate's expr expresses "abc occurs exactly
        # twice in region_VAR" as nested str.indexof calls — the second
        # indexof's start offset is the first match's position + len(sub),
        # so the rewrite must reference str.indexof at least twice and
        # carry no replace_all / div remnants.
        assert not _expr_contains_op(expr, "str.replace_all"), (
            "expected rewrite to drop the str.replace_all+div form for k=2; "
            f"still present in {expr!r}"
        )
        assert not _expr_contains_op(expr, "div"), (
            f"expected rewrite to drop the div node for k=2; still present in {expr!r}"
        )

        # Count str.indexof occurrences — the chained form for k=2 needs
        # at least 2 indexof calls (one per match).
        indexof_count = _count_op_occurrences(expr, "str.indexof")
        assert indexof_count >= 2, (
            f"expected at least 2 str.indexof calls for k=2 chained rewrite; "
            f"got {indexof_count} in {expr!r}"
        )


def _count_op_occurrences(node, op: str) -> int:
    """Count list-nodes whose head is ``op`` anywhere in the tree."""
    if not isinstance(node, list):
        return 0
    hit = 1 if node and node[0] == op else 0
    return hit + sum(_count_op_occurrences(child, op) for child in node)


# ---------------------------------------------------------------------------
# Test 4 — symbolic sub falls back to the baseline encoding
# ---------------------------------------------------------------------------


class TestCountSymbolicSubFallsBack:
    """Symbolic ``sub`` skips the rewrite and increments the skip counter."""

    def test_symbolic_sub_preserves_original_and_bumps_skip_counter(self):
        from pyct.engine import constraint_optimizer

        state = ExplorationState()
        # Symbolic sub: a bare SMT var name (no py2smt-wrapped quotes).
        symbolic_sub = "sub_VAR"
        constraint = _eq_count_constraint("region_VAR", symbolic_sub, 0)
        original_expr = constraint.predicate.expr

        rewritten = constraint_optimizer.optimize(constraint, state)
        rewritten_expr = _rewritten_expr(rewritten)

        # Original shape must survive — the rewrite rule only fires
        # when sub is a literal string. With a symbolic sub the
        # optimizer must leave the replace_all+div form in place so the
        # baseline encoding still drives the solver.
        assert _expr_contains_op(rewritten_expr, "str.replace_all"), (
            "expected symbolic-sub constraint to keep the replace_all encoding; "
            f"rewritten expr lost it: {rewritten_expr!r}"
        )
        assert _expr_contains_op(rewritten_expr, "div"), (
            "expected symbolic-sub constraint to keep the div node; "
            f"rewritten expr lost it: {rewritten_expr!r}"
        )

        # Skip counter must bump once per symbolic-sub encounter so
        # downstream telemetry can attribute "rewrite didn't fire here".
        assert getattr(state, "gen_count_skipped_symbolic_sub", 0) == 1, (
            "expected gen_count_skipped_symbolic_sub to bump to 1 on symbolic-sub "
            f"fallback; got {getattr(state, 'gen_count_skipped_symbolic_sub', 'ATTRIBUTE-MISSING')!r}. "
            f"Original expr was: {original_expr!r}"
        )


# ---------------------------------------------------------------------------
# Test 5 — empty-string sub preserves the existing ITE-empty arm
# ---------------------------------------------------------------------------


class TestCountEmptySubPreservesSemantics:
    """``count("")`` must keep the ``len + 1`` semantics — no contains-collapse."""

    def test_empty_sub_does_not_collapse_to_not_contains(self):
        from pyct.engine import constraint_optimizer

        state = ExplorationState()
        # Literal empty-string sub — the rewrite to (not (str.contains s ""))
        # would silently change semantics because Python defines
        # `"abc".count("") == len("abc") + 1`, not 0.
        constraint = _eq_count_constraint("region_VAR", py2smt(""), 0)

        rewritten = constraint_optimizer.optimize(constraint, state)
        expr = _rewritten_expr(rewritten)

        # The empty-sub arm of the original ITE — `(+ 1 (str.len region))`
        # — must remain reachable in the rewritten expr. A naive
        # collapse to `(not (str.contains region ""))` would drop this
        # arm entirely and the optimizer must guard against it.
        flat_contains_only = (
            isinstance(expr, list)
            and expr
            and expr[0] == "not"
            and isinstance(expr[1], list)
            and expr[1]
            and expr[1][0] == "str.contains"
        )
        assert not flat_contains_only, (
            "expected empty-sub count NOT to collapse to (not (str.contains ...)); "
            f"that loses Python's `s.count('') == len(s) + 1` semantics. got {expr!r}"
        )
        # The +1+str.len arm (or an equivalent fragment that preserves
        # the empty-sub branch) must still be derivable from the expr.
        # Easiest structural witness: the constant "1" appears under a
        # `+` head whose other operand is a `str.len` term.
        assert _expr_contains(expr, ["+", "1", ["str.len", "region_VAR"]]), (
            "expected the empty-sub ITE arm `(+ 1 (str.len region))` to be "
            f"preserved in the rewritten expr; got {expr!r}"
        )


# ---------------------------------------------------------------------------
# Test 6 — the firing counter bumps once per successful rewrite
# ---------------------------------------------------------------------------


class TestCountCounterFires:
    """``gen_count_rewritten`` bumps once at every substitution site."""

    def test_zero_rewrite_increments_counter(self):
        from pyct.engine import constraint_optimizer

        state = ExplorationState()
        constraint = _eq_count_constraint("region_VAR", py2smt("abc"), 0)

        constraint_optimizer.optimize(constraint, state)

        assert getattr(state, "gen_count_rewritten", 0) == 1, (
            "expected gen_count_rewritten to bump to 1 after a successful "
            "count(sub)==0 rewrite; got "
            f"{getattr(state, 'gen_count_rewritten', 'ATTRIBUTE-MISSING')!r}."
        )


# ---------------------------------------------------------------------------
# Test 7 — case-fold ASCII rewrite substitutes a charwise SMT form
# ---------------------------------------------------------------------------


def _case_fold_lower_expr(s_var: str) -> list:
    """Build the 26-deep replace_all chain that ``CaseConverter.to_lower`` emits.

    Mirrors ``core/str/helpers.py:CaseConverter.to_lower`` so tests feed the
    optimizer the same tree the engine would emit at runtime for ``s.lower()``.
    """
    expr: Any = s_var
    for i in range(65, 91):  # 'A' .. 'Z'
        expr = ["str.replace_all", expr, py2smt(chr(i)), py2smt(chr(i + 32))]
    return expr


def _eq_case_fold_constraint(s_var: str, literal: str) -> Constraint:
    """Wrap ``(= <case_fold_lower_expr> "<literal>")`` in a fresh path Constraint."""
    expr = ["=", _case_fold_lower_expr(s_var), py2smt(literal)]
    root = Constraint(parent_id=None, predicate=None)
    return root.add_child(Predicate(expr, True))


class TestCaseFoldAsciiSubstitutesCharwise:
    """``s.lower() == "<ascii>"`` collapses to a char-wise length+equality form."""

    def test_lower_equals_ascii_rewrites_to_charwise(self):
        from pyct.engine import constraint_optimizer

        state = ExplorationState()
        constraint = _eq_case_fold_constraint("s_VAR", "monday")

        rewritten = constraint_optimizer.optimize(constraint, state)
        expr = _rewritten_expr(rewritten)

        # Post-green the predicate's expr drops the 26-deep replace_all
        # chain entirely and expresses the equality char-wise:
        #   (and (= (str.len s_VAR) 6)
        #        (or (= (str.at s_VAR 0) "m") (= (str.at s_VAR 0) "M"))
        #        ...)
        assert not _expr_contains_op(expr, "str.replace_all"), (
            "expected case-fold rewrite to drop the 26-deep replace_all chain; "
            f"still present in {expr!r}"
        )
        # str.at must appear at least once per literal char (6 for "monday").
        at_count = _count_op_occurrences(expr, "str.at")
        assert at_count >= 6, (
            f"expected at least 6 str.at calls for 6-char literal; got {at_count} in {expr!r}"
        )
        # str.len constraint pins the input length to len("monday") == 6.
        assert _expr_contains(expr, ["str.len", "s_VAR"]), (
            f"expected (str.len s_VAR) to anchor the length constraint; got {expr!r}"
        )
        assert _expr_contains(expr, "6"), (
            f"expected the literal length 6 to appear in the rewrite; got {expr!r}"
        )


# ---------------------------------------------------------------------------
# Test 8 — the case-fold firing counter bumps once per successful rewrite
# ---------------------------------------------------------------------------


class TestCaseFoldCounterFires:
    """``gen_case_fold_rewritten`` bumps once at every substitution site."""

    def test_ascii_rewrite_increments_counter(self):
        from pyct.engine import constraint_optimizer

        state = ExplorationState()
        constraint = _eq_case_fold_constraint("s_VAR", "monday")

        constraint_optimizer.optimize(constraint, state)

        assert getattr(state, "gen_case_fold_rewritten", 0) == 1, (
            "expected gen_case_fold_rewritten to bump to 1 after a successful "
            "case-fold ASCII rewrite; got "
            f"{getattr(state, 'gen_case_fold_rewritten', 'ATTRIBUTE-MISSING')!r}."
        )


# ---------------------------------------------------------------------------
# Test 9 — case-fold counter ticks with exact firing counts per ASCII shape
# ---------------------------------------------------------------------------


class TestCaseFoldCounterFiresWithExactCounts:
    """``gen_case_fold_rewritten`` counts every successful ASCII rewrite."""

    def test_three_independent_rewrites_bump_counter_three(self):
        from pyct.engine import constraint_optimizer

        state = ExplorationState()
        for literal in ("monday", "x", "AbCdEf"):
            constraint = _eq_case_fold_constraint("s_VAR", literal)
            constraint_optimizer.optimize(constraint, state)

        assert state.gen_case_fold_rewritten == 3, (
            "expected gen_case_fold_rewritten == 3 after three independent "
            f"ASCII rewrites; got {state.gen_case_fold_rewritten}"
        )

    def test_no_state_runs_no_op_for_counter(self):
        """``optimize(constraint, None)`` rewrites without touching counters."""
        from pyct.engine import constraint_optimizer

        constraint = _eq_case_fold_constraint("s_VAR", "monday")
        rewritten = constraint_optimizer.optimize(constraint, None)

        # Expr still got rewritten — the rule fires even without state.
        assert not _expr_contains_op(_rewritten_expr(rewritten), "str.replace_all"), (
            "expected case-fold rewrite to still drop replace_all chain "
            "when state is None; got tree with replace_all surviving."
        )


# ---------------------------------------------------------------------------
# Test 10 — non-ASCII case-fold literal preserves the replace_all chain
# ---------------------------------------------------------------------------


class TestCaseFoldNonAsciiFallsBack:
    """Non-ASCII compared literals leave the chain intact and bump skip counter."""

    def test_non_ascii_literal_keeps_replace_all_and_bumps_skip(self):
        from pyct.engine import constraint_optimizer

        state = ExplorationState()
        constraint = _eq_case_fold_constraint("s_VAR", "café")
        original_expr = constraint.predicate.expr

        rewritten = constraint_optimizer.optimize(constraint, state)
        rewritten_expr = _rewritten_expr(rewritten)

        # Non-ASCII literal MUST NOT trigger the charwise rewrite — the
        # rule is unsound for Unicode letters (Python case-folds via
        # Unicode case mappings, not the 26-deep ASCII chain). The
        # original replace_all chain must survive unchanged.
        assert _expr_contains_op(rewritten_expr, "str.replace_all"), (
            "expected non-ASCII case-fold constraint to keep the 26-deep "
            f"replace_all chain; rewritten expr lost it: {rewritten_expr!r}"
        )
        # Skip counter must bump once per non-ASCII fallback so downstream
        # telemetry can attribute "rewrite didn't fire here".
        assert getattr(state, "gen_case_fold_skipped_non_ascii", 0) == 1, (
            "expected gen_case_fold_skipped_non_ascii to bump to 1 on "
            "non-ASCII fallback; got "
            f"{getattr(state, 'gen_case_fold_skipped_non_ascii', 'ATTRIBUTE-MISSING')!r}. "
            f"Original expr was: {original_expr!r}"
        )
        # The firing counter MUST NOT bump on the skip path.
        assert state.gen_case_fold_rewritten == 0, (
            "expected gen_case_fold_rewritten to stay at 0 on non-ASCII "
            f"skip path; got {state.gen_case_fold_rewritten}"
        )

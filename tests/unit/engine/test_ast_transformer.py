"""Unit tests for the concolic AST transformer.

The transformer rewrites target source at load time so that Python's
built-in ``int()``, ``str()``, ``range()``, and ``is`` comparisons route
through our symbolic helpers instead of CPython's C-level fast paths
(which strip concolic wrappers). This mirrors upstream PyCT's
``libct/wrapper.py`` design but is scoped down to the rewrites we
currently need.

Tests cover:
- Happy path: each rewrite produces the expected qualified call
- Pass-through: unrelated calls are not touched
- Edge cases: ``int(x, 16)`` with a base argument is left alone
- Nesting: ``int(str(x))`` becomes ``_int(_str(x))``
- Line preservation: rewritten nodes inherit the original line numbers
"""

from __future__ import annotations

import ast
import textwrap

import pytest


@pytest.fixture
def rewrite():
    """Return a helper that parses source, rewrites, and unparses."""
    from pyct.engine.ast_transformer import ConcolicCallRewriter, ConcolicCompareRewriter

    def _rewrite(source: str) -> str:
        tree = ast.parse(textwrap.dedent(source))
        tree = ConcolicCallRewriter().visit(tree)
        tree = ConcolicCompareRewriter().visit(tree)
        ast.fix_missing_locations(tree)
        return ast.unparse(tree)

    return _rewrite


class TestCallRewrite:
    def test_int_call_rewritten_to_helper(self, rewrite):
        out = rewrite("x = int(s)")
        assert "pyct.core.builtin_wrappers._int(s)" in out

    def test_str_call_rewritten_to_helper(self, rewrite):
        out = rewrite("x = str(n)")
        assert "pyct.core.builtin_wrappers._str(n)" in out

    def test_range_call_rewritten_to_concolic_range(self, rewrite):
        out = rewrite("for _ in range(n): pass")
        assert "pyct.core.concolic_range.ConcolicRange(n)" in out

    def test_range_with_start_stop_step_rewritten(self, rewrite):
        out = rewrite("for _ in range(a, b, c): pass")
        assert "pyct.core.concolic_range.ConcolicRange(a, b, c)" in out

    def test_int_with_base_left_alone(self, rewrite):
        """int(x, 16) has a base argument — upstream leaves it untouched."""
        out = rewrite("x = int(s, 16)")
        assert "pyct.core.builtin_wrappers._int" not in out
        assert "int(s, 16)" in out

    def test_str_with_encoding_left_alone(self, rewrite):
        out = rewrite("x = str(s, 'utf-8')")
        assert "pyct.core.builtin_wrappers._str" not in out

    def test_unrelated_call_passes_through(self, rewrite):
        out = rewrite("x = foo(n)")
        assert "foo(n)" in out
        assert "builtin_wrappers" not in out
        assert "concolic_range" not in out

    def test_nested_int_of_str_rewritten(self, rewrite):
        out = rewrite("x = int(str(n))")
        assert "_int(pyct.core.builtin_wrappers._str(n))" in out

    def test_int_no_args_left_alone(self, rewrite):
        """int() with no args returns 0 — not our concern."""
        out = rewrite("x = int()")
        assert "pyct.core.builtin_wrappers._int" not in out

    def test_method_call_not_rewritten(self, rewrite):
        """obj.int() is a method call, not the builtin — leave alone."""
        out = rewrite("x = obj.int(n)")
        assert "pyct.core.builtin_wrappers._int" not in out
        assert "obj.int(n)" in out


class TestCompareRewrite:
    """Rewrite only ``x is <literal>`` comparisons.

    The rewrite covers the 99% ``x is None`` / ``x is True`` / ``x is False``
    idiom while leaving genuine object-identity checks (``x is y`` where ``y``
    is a variable or call result) untouched. Variable-RHS identity checks go
    through Python's default ``is`` semantics, which matches the user's
    intent when they wrote ``is`` instead of ``==``.
    """

    def test_is_none_rewritten(self, rewrite):
        out = rewrite("result = x is None")
        assert "pyct.core.builtin_wrappers._is(x, None)" in out

    def test_is_true_rewritten(self, rewrite):
        out = rewrite("result = x is True")
        assert "pyct.core.builtin_wrappers._is(x, True)" in out

    def test_is_false_rewritten(self, rewrite):
        out = rewrite("result = x is False")
        assert "pyct.core.builtin_wrappers._is(x, False)" in out

    def test_is_ellipsis_rewritten(self, rewrite):
        out = rewrite("result = x is ...")
        assert "pyct.core.builtin_wrappers._is(x, ...)" in out

    def test_is_variable_NOT_rewritten(self, rewrite):
        """``x is y`` where ``y`` is a variable preserves Python identity
        semantics — different object references must remain distinct, and
        the concolic layer can't model identity without unwrap semantics
        that diverge from user expectation."""
        out = rewrite("result = x is y")
        assert "builtin_wrappers" not in out
        assert "x is y" in out

    def test_is_function_call_NOT_rewritten(self, rewrite):
        """``x is foo()`` — function call RHS is not a literal."""
        out = rewrite("result = x is foo()")
        assert "builtin_wrappers" not in out

    def test_is_integer_literal_NOT_rewritten(self, rewrite):
        """``x is 5`` is a Python anti-pattern (use ==) but we shouldn't
        rewrite it — integer interning makes it ambiguous and the user's
        intent is usually a typo anyway."""
        out = rewrite("result = x is 5")
        assert "builtin_wrappers" not in out

    def test_eq_comparison_not_rewritten(self, rewrite):
        out = rewrite("result = x == y")
        assert "builtin_wrappers" not in out
        assert "x == y" in out

    def test_is_not_left_alone(self, rewrite):
        """Upstream's transformer only handles single `is`, not `is not`."""
        out = rewrite("result = x is not None")
        assert "pyct.core.builtin_wrappers._is" not in out

    def test_chained_comparison_left_alone(self, rewrite):
        """a < b < c has multiple comparators — not a single `is` pattern."""
        out = rewrite("result = a < b < c")
        assert "a < b < c" in out


class TestLinePreservation:
    def test_rewritten_int_call_keeps_line_number(self):
        from pyct.engine.ast_transformer import ConcolicCallRewriter

        source = "def f(s):\n    return int(s)\n"
        tree = ast.parse(source)
        tree = ConcolicCallRewriter().visit(tree)
        ast.fix_missing_locations(tree)

        call_nodes = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
        assert call_nodes, "no Call nodes after rewrite"
        top_call = call_nodes[0]
        assert top_call.lineno == 2, (
            f"expected line 2 for the rewritten call, got {top_call.lineno}"
        )

    def test_rewritten_range_keeps_line_number(self):
        from pyct.engine.ast_transformer import ConcolicCallRewriter

        source = "def f(n):\n    for _ in range(n):\n        pass\n"
        tree = ast.parse(source)
        tree = ConcolicCallRewriter().visit(tree)
        ast.fix_missing_locations(tree)

        call_nodes = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
        assert call_nodes, "no Call nodes after rewrite"
        assert any(c.lineno == 2 for c in call_nodes), (
            f"no rewritten node at line 2, got {[c.lineno for c in call_nodes]}"
        )


_TEST_MODULE_CONSTANT = 100


def _target_parses_int(s):
    return int(s)


def _target_uses_module_globals(x):
    return x + _TEST_MODULE_CONSTANT


class TestRewriteTarget:
    def test_rewrite_target_returns_callable_with_same_name(self):
        from pyct.engine.ast_transformer import rewrite_target

        rewritten = rewrite_target(_target_parses_int)
        assert callable(rewritten)
        assert rewritten.__name__ == "_target_parses_int"

    def test_rewrite_target_int_call_routes_through_helper(self, monkeypatch):
        """Concrete smoke test: calling rewritten target invokes _int.

        Monkeypatches the helper with a marker so we can detect that
        the rewrite actually ran — not just that the function compiled.
        """
        import pyct.core.builtin_wrappers as bw

        calls: list = []
        original_int = bw._int
        monkeypatch.setattr(bw, "_int", lambda x: calls.append(("_int", x)) or original_int(x))

        from pyct.engine.ast_transformer import rewrite_target

        rewritten = rewrite_target(_target_parses_int)
        result = rewritten("42")
        assert result == 42
        assert calls == [("_int", "42")]

    def test_rewrite_target_preserves_access_to_module_globals(self):
        """Rewritten target must still resolve module-level names.

        The rewrite exec's the function source in the target's own
        ``__globals__``, so module-level constants, imports, and other
        helpers remain accessible. Closures over local variables do
        not survive (documented limitation — benchmark targets are
        top-level functions).
        """
        from pyct.engine.ast_transformer import rewrite_target

        rewritten = rewrite_target(_target_uses_module_globals)
        assert rewritten(5) == 105


class TestRewriteTargetErrorPaths:
    """Ensure rewrite failures surface as TypeError so explore() catches them."""

    def test_lambda_rejected_upfront(self):
        """Lambdas must be rejected BEFORE we exec the rewritten source.

        ``inspect.getsource`` on a lambda returns the entire containing
        statement, not just the ``lambda`` expression. Exec-ing that
        source would re-run the caller — including, in the common case
        ``engine.explore(lambda x: ..., {...})``, a recursive call
        back into the engine that would infinite-loop. Reject the
        lambda before any source extraction happens.
        """
        import pytest

        from pyct.engine.ast_transformer import rewrite_target

        lam = lambda x: x + 1  # noqa: E731
        with pytest.raises(TypeError, match="lambda"):
            rewrite_target(lam)

    def test_inline_lambda_argument_does_not_recurse(self):
        """Reproduction of a real recursion bug: passing a lambda as an
        inline argument to engine.explore would cause rewrite_target to
        extract and exec the entire caller line, which re-invokes
        engine.explore → infinite recursion. Must raise TypeError cleanly.
        """
        from pyct import Engine
        from pyct.config.execution import ExecutionConfig

        engine = Engine(ExecutionConfig())
        result = engine.explore(lambda x: x + 1, {"x": 0})
        # Engine.explore catches TypeError from rewrite_target and returns
        # a clean error_result.
        assert result.success is False
        assert result.termination_reason == "error"
        assert "lambda" in (result.error or "").lower()

    def test_syntaxerror_in_rewrite_raises_type_error(self, monkeypatch):
        """A SyntaxError from ast.parse (pathological, but possible if
        inspect.getsource returns something weird) must surface as
        TypeError, not a bare SyntaxError that escapes explore()."""
        import inspect

        import pytest

        from pyct.engine import ast_transformer

        def _broken_source(_target):
            return "def broken(x:\n    return x"

        monkeypatch.setattr(inspect, "getsource", _broken_source)

        with pytest.raises(TypeError, match="rewrite"):
            ast_transformer.rewrite_target(_target_parses_int)

    def test_shift_line_numbers_warns_on_getsourcelines_failure(self, monkeypatch, caplog):
        """If getsourcelines fails in _shift_line_numbers after getsource
        already succeeded (pathological — file racing, linecache quirk),
        coverage attribution would be silently empty. We must log a
        WARNING so the issue has a visible breadcrumb.

        Tests _shift_line_numbers directly rather than rewrite_target to
        isolate the branch — rewrite_target calls getsource first, which
        would fail through the same mock and short-circuit the test.
        """
        import ast
        import inspect
        import logging

        from pyct.engine import ast_transformer

        def _broken_getsourcelines(_target):
            raise OSError("source temporarily unavailable")

        monkeypatch.setattr(inspect, "getsourcelines", _broken_getsourcelines)

        tree = ast.parse("def f(x):\n    return x\n")
        with caplog.at_level(logging.WARNING, logger="ct.engine.ast_transformer"):
            ast_transformer._shift_line_numbers(tree, _target_parses_int)

        assert any("line shift unavailable" in r.message for r in caplog.records)

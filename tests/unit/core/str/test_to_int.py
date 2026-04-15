"""Unit tests for ConcolicStr.to_int — symbolic int() parsing.

Ported from upstream ``libct/concolic/str.py::__int2__``, adapted to
the ``to_*`` naming convention used elsewhere in this codebase. The
symbolic expression uses SMT-LIB2's ``str.to.int`` with an ``ite``
branch for leading-minus handling (because ``str.to.int`` is defined
only for non-negative digit strings and returns -1 for any other
input, we handle signed strings explicitly).

Tests cover happy (positive/zero/negative parsing), edge (whitespace
behavior matching Python's int()), and error (non-numeric strings).
"""

from __future__ import annotations

import pytest


class TestToIntConcrete:
    """Concrete parsing behavior must match Python's int()."""

    def test_positive_integer(self, engine):
        from pyct.core.str.str import ConcolicStr

        cs = ConcolicStr("42", "s_VAR", engine)
        result = cs.to_int()
        assert int(result) == 42

    def test_zero(self, engine):
        from pyct.core.str.str import ConcolicStr

        cs = ConcolicStr("0", "s_VAR", engine)
        result = cs.to_int()
        assert int(result) == 0

    def test_negative_integer(self, engine):
        from pyct.core.str.str import ConcolicStr

        cs = ConcolicStr("-42", "s_VAR", engine)
        result = cs.to_int()
        assert int(result) == -42

    def test_raises_on_non_numeric(self, engine):
        from pyct.core.str.str import ConcolicStr

        cs = ConcolicStr("hello", "s_VAR", engine)
        with pytest.raises(ValueError, match="invalid literal"):
            cs.to_int()

    def test_raises_on_empty_string(self, engine):
        from pyct.core.str.str import ConcolicStr

        cs = ConcolicStr("", "s_VAR", engine)
        with pytest.raises(ValueError):
            cs.to_int()


class TestToIntSymbolic:
    """Symbolic expression structure for the solver."""

    def test_returns_concolic_int(self, engine):
        from pyct.core.int import ConcolicInt
        from pyct.core.str.str import ConcolicStr

        cs = ConcolicStr("42", "s_VAR", engine)
        result = cs.to_int()
        assert isinstance(result, ConcolicInt)

    def test_expression_is_ite_for_sign_handling(self, engine):
        """The symbolic expression must handle negative strings via ite.

        Upstream's template (libct/concolic/str.py:1321-1331) uses an
        ite branching on str.prefixof "-" so that negative inputs route
        through a subtraction; this lets CVC5 model the sign correctly
        without hitting str.to.int's -1 sentinel for negative strings.
        """
        from pyct.core.str.str import ConcolicStr

        cs = ConcolicStr("42", "s_VAR", engine)
        result = cs.to_int()
        assert result.expr[0] == "ite"
        assert result.expr[1][0] == "str.prefixof"

    def test_expression_references_source_string(self, engine):
        """The symbolic expression must reference the source ConcolicStr
        (not a copy) so the solver can unify constraints on it."""
        from pyct.core.str.str import ConcolicStr

        cs = ConcolicStr("42", "s_VAR", engine)
        result = cs.to_int()
        # The ite's 'else' branch is ["str.to_int", self] — self must be cs
        else_branch = result.expr[3]
        assert else_branch[0] == "str.to_int"
        assert else_branch[1] is cs

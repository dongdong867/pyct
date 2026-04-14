"""Tests for Concolic mixin and MetaFinal metaclass."""

from __future__ import annotations

import pickle

import pytest

from pyct.core import Concolic, has_symbolic_expression, is_concolic
from pyct.core.bool import ConcolicBool
from pyct.core.int import ConcolicInt
from pyct.core.str.str import ConcolicStr


class TestConcolicIsSymbolic:
    """Concolic.is_symbolic / is_concrete based on engine + expr."""

    def test_symbolic_with_engine_and_expr(self, engine):
        ci = ConcolicInt(42, "x", engine)
        assert ci.is_symbolic()
        assert not ci.is_concrete()

    def test_concrete_without_engine(self):
        ci = ConcolicInt(42)
        assert ci.is_concrete()
        assert not ci.is_symbolic()

    def test_concrete_when_expr_equals_value(self, engine):
        ci = ConcolicInt(42, None, engine)
        assert ci.is_concrete()


class TestFindEngineInExpr:
    """Concolic.find_engine_in_expr recursive search."""

    def test_finds_engine_in_concolic_object(self, engine):
        ci = ConcolicInt(1, "x", engine)
        assert Concolic.find_engine_in_expr(ci) is engine

    def test_finds_engine_in_nested_list(self, engine):
        ci = ConcolicInt(1, "x", engine)
        expr = ["and", ["or", ci, "y"], "z"]
        assert Concolic.find_engine_in_expr(expr) is engine

    def test_returns_none_for_plain_values(self):
        assert Concolic.find_engine_in_expr("x") is None
        assert Concolic.find_engine_in_expr(42) is None
        assert Concolic.find_engine_in_expr(None) is None

    def test_returns_none_for_list_without_engine(self):
        assert Concolic.find_engine_in_expr(["and", "x", "y"]) is None


class TestConcolicPickle:
    """Pickle strips engine reference and restores state."""

    def test_pickle_strips_engine(self, engine):
        ci = ConcolicInt(42, "x", engine)
        assert ci.engine is engine

        pickled = pickle.dumps(ci)
        restored = pickle.loads(pickled)

        assert int(restored) == 42
        assert restored.engine is None

    def test_pickle_preserves_value_and_expr(self, engine):
        ci = ConcolicInt(42, "x", engine)
        restored = pickle.loads(pickle.dumps(ci))
        assert restored.value == ci.value
        assert restored.expr == "x"


class TestConcolicRepr:
    """__repr__ shows type-specific format (subclasses override base repr)."""

    def test_concolic_int_repr(self, engine):
        ci = ConcolicInt(42, "x", engine)
        assert repr(ci) == "ConcolicInt(42)"

    def test_concolic_bool_repr(self, engine):
        cb = ConcolicBool(True, "x", engine)
        assert repr(cb) == "ConcolicBool(True)"


class TestMetaFinal:
    """MetaFinal prevents subclassing."""

    def test_prevents_subclassing_concolic_int(self):
        with pytest.raises(TypeError, match="Cannot subclass final type"):
            type("SubInt", (ConcolicInt,), {})

    def test_prevents_subclassing_concolic_str(self):
        with pytest.raises(TypeError, match="Cannot subclass final type"):
            type("SubStr", (ConcolicStr,), {})

    def test_prevents_subclassing_concolic_bool(self):
        with pytest.raises(TypeError, match="Cannot subclass final type"):
            type("SubBool", (ConcolicBool,), {})


class TestHelperFunctions:
    """Module-level is_concolic / has_symbolic_expression."""

    def test_is_concolic_true(self, engine):
        assert is_concolic(ConcolicInt(1, "x", engine))

    def test_is_concolic_false_for_plain(self):
        assert not is_concolic(42)
        assert not is_concolic("hello")

    def test_has_symbolic_expression(self, engine):
        ci = ConcolicInt(1, "x", engine)
        assert has_symbolic_expression(ci)

    def test_has_symbolic_expression_false_concrete(self):
        ci = ConcolicInt(1)
        assert not has_symbolic_expression(ci)

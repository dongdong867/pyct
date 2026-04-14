"""Tests for ConcolicStr: construction, comparisons, bool, iteration."""

from __future__ import annotations

from pyct.core.str.str import ConcolicStr
from pyct.utils.concolic_converter import unwrap_concolic


class TestConstruction:
    """ConcolicStr creation from various value types."""

    def test_create_from_str(self, engine):
        cs = ConcolicStr("hello", "x", engine)
        assert str(cs) == "hello"
        assert cs.is_symbolic()

    def test_create_concrete(self):
        cs = ConcolicStr("world")
        assert str(cs) == "world"
        assert cs.is_concrete()

    def test_create_from_non_string(self):
        cs = ConcolicStr(42)
        assert str(cs) == "42"


class TestComparisons:
    """String equality and ordering comparisons."""

    def test_eq_true(self, engine):
        a = ConcolicStr("abc", "a", engine)
        b = ConcolicStr("abc", "b", engine)
        result = a == b
        assert unwrap_concolic(result) is True
        assert result.expr == ["=", a, b]

    def test_eq_false(self, engine):
        a = ConcolicStr("abc", "a", engine)
        result = a == "xyz"
        assert unwrap_concolic(result) is False

    def test_ne(self, engine):
        a = ConcolicStr("abc", "a", engine)
        b = ConcolicStr("xyz", "b", engine)
        result = a != b
        assert unwrap_concolic(result) is True
        assert result.expr == ["not", ["=", a, b]]

    def test_lt(self, engine):
        a = ConcolicStr("abc", "a", engine)
        b = ConcolicStr("xyz", "b", engine)
        result = a < b
        assert unwrap_concolic(result) is True

    def test_gt(self, engine):
        a = ConcolicStr("xyz", "a", engine)
        b = ConcolicStr("abc", "b", engine)
        result = a > b
        assert unwrap_concolic(result) is True


class TestBoolConversion:
    """__bool__ non-empty check."""

    def test_bool_nonempty_true(self, engine):
        cs = ConcolicStr("hello", "x", engine)
        assert bool(cs) is True

    def test_bool_empty_false(self, engine):
        cs = ConcolicStr("", "x", engine)
        assert bool(cs) is False


class TestIteration:
    """__iter__ yields ConcolicStr characters."""

    def test_iter_yields_chars(self, engine):
        cs = ConcolicStr("abc", "x", engine)
        chars = list(cs)
        assert len(chars) == 3
        assert unwrap_concolic(chars[0]) == "a"
        assert unwrap_concolic(chars[1]) == "b"
        assert unwrap_concolic(chars[2]) == "c"

    def test_iter_empty_string(self, engine):
        cs = ConcolicStr("", "x", engine)
        assert list(cs) == []


class TestConstructionEdgeCases:
    """Boundary and permissive construction."""

    def test_create_from_none_coerces_to_string(self):
        cs = ConcolicStr(None)
        assert str(cs) == "None"

    def test_create_from_list_coerces_to_repr(self):
        cs = ConcolicStr([1, 2, 3])
        assert str(cs) == "[1, 2, 3]"

    def test_eq_with_different_primitive_type_returns_false(self, engine):
        cs = ConcolicStr("42", "x", engine)
        # Comparing to an int — should not raise, should return False
        result = cs == 42
        assert unwrap_concolic(result) is False

"""Tests for ConcolicFloat."""

from __future__ import annotations

import math

import pytest

from pyct.core.float import ConcolicFloat
from pyct.core.int import ConcolicInt
from pyct.utils.concolic_converter import unwrap_concolic


class TestConstruction:
    """ConcolicFloat creation from various value types."""

    def test_from_float(self, engine):
        cf = ConcolicFloat(3.14, "x", engine)
        assert float(cf) == pytest.approx(3.14)
        assert cf.is_symbolic()

    def test_from_int(self):
        cf = ConcolicFloat(5)
        assert float(cf) == 5.0

    def test_with_expr_and_engine_is_symbolic(self, engine):
        cf = ConcolicFloat(2.5, "y", engine)
        assert cf.is_symbolic()
        assert cf.expr == "y"
        assert cf.engine is engine

    def test_without_engine_is_concrete(self):
        cf = ConcolicFloat(2.5)
        assert cf.is_concrete()


class TestArithmetic:
    """Arithmetic operations on ConcolicFloat."""

    def test_truediv(self, engine):
        a = ConcolicFloat(10.0, "a", engine)
        b = ConcolicFloat(3.0, "b", engine)
        result = a / b
        assert unwrap_concolic(result) == pytest.approx(10.0 / 3.0)
        assert result.expr == ["/", a, b]

    def test_mixed_with_int(self, engine):
        cf = ConcolicFloat(10.0, "x", engine)
        result = cf / 2
        assert unwrap_concolic(result) == pytest.approx(5.0)

    def test_mixed_with_concolic_int(self, engine):
        cf = ConcolicFloat(10.0, "x", engine)
        ci = ConcolicInt(3, "y", engine)
        result = cf / ci
        assert unwrap_concolic(result) == pytest.approx(10.0 / 3)


class TestComparisons:
    """Comparison operations on ConcolicFloat."""

    def test_eq(self, engine):
        a = ConcolicFloat(3.14, "a", engine)
        b = ConcolicFloat(3.14, "b", engine)
        result = a == b
        assert unwrap_concolic(result) is True
        assert result.expr == ["=", a, b]

    def test_lt(self, engine):
        a = ConcolicFloat(2.0, "a", engine)
        b = ConcolicFloat(3.0, "b", engine)
        result = a < b
        assert unwrap_concolic(result) is True
        assert result.expr == ["<", a, b]

    def test_gt(self, engine):
        a = ConcolicFloat(5.0, "a", engine)
        b = ConcolicFloat(3.0, "b", engine)
        result = a > b
        assert unwrap_concolic(result) is True
        assert result.expr == [">", a, b]

    def test_le(self, engine):
        a = ConcolicFloat(3.0, "a", engine)
        b = ConcolicFloat(3.0, "b", engine)
        result = a <= b
        assert unwrap_concolic(result) is True
        assert result.expr == ["<=", a, b]

    def test_ge(self, engine):
        a = ConcolicFloat(3.0, "a", engine)
        b = ConcolicFloat(3.0, "b", engine)
        result = a >= b
        assert unwrap_concolic(result) is True
        assert result.expr == [">=", a, b]

    def test_ne(self, engine):
        a = ConcolicFloat(3.0, "a", engine)
        b = ConcolicFloat(4.0, "b", engine)
        result = a != b
        assert unwrap_concolic(result) is True
        assert result.expr == ["not", ["=", a, b]]

    def test_comparison_with_int(self, engine):
        cf = ConcolicFloat(3.14, "x", engine)
        result = cf > 3
        assert unwrap_concolic(result) is True


class TestTypeConversion:
    """to_int, to_float, __bool__, __int__."""

    def test_to_int_truncates(self, engine):
        cf = ConcolicFloat(3.7, "x", engine)
        ci = cf.to_int()
        assert isinstance(ci, ConcolicInt)
        assert int(ci) == 3

    def test_to_int_negative_truncates_toward_zero(self, engine):
        cf = ConcolicFloat(-2.5, "x", engine)
        ci = cf.to_int()
        assert int(ci) == -2

    def test_to_float_returns_self(self, engine):
        cf = ConcolicFloat(3.14, "x", engine)
        assert cf.to_float() is cf

    def test_bool_zero_false(self):
        cf = ConcolicFloat(0.0)
        assert bool(cf) is False

    def test_bool_nonzero_true(self):
        cf = ConcolicFloat(1.5)
        assert bool(cf) is True

    def test_int_builtin(self):
        cf = ConcolicFloat(3.7)
        assert int(cf) == 3


class TestEdgeCases:
    """NaN, infinity, negative zero, very small floats."""

    def test_nan(self):
        cf = ConcolicFloat(float("nan"))
        assert math.isnan(float(cf))

    def test_infinity(self):
        cf = ConcolicFloat(float("inf"))
        assert math.isinf(float(cf))

    def test_negative_zero(self):
        cf = ConcolicFloat(-0.0)
        assert float(cf) == 0.0

    def test_very_small_float(self):
        cf = ConcolicFloat(1e-300)
        assert float(cf) == pytest.approx(1e-300)

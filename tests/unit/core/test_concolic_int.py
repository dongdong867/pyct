"""Tests for ConcolicInt."""

from __future__ import annotations

import pickle


from pyct.core.float import ConcolicFloat
from pyct.core.int import ConcolicInt
from pyct.utils.concolic_converter import unwrap_concolic


class TestConstruction:
    """ConcolicInt creation from various value types."""

    def test_from_int_literal(self, engine):
        ci = ConcolicInt(42, "x", engine)
        assert int(ci) == 42
        assert ci.is_symbolic()

    def test_from_float_truncates(self):
        ci = ConcolicInt(3.7)
        assert int(ci) == 3

    def test_from_bool_normalizes(self):
        ci = ConcolicInt(True)
        assert int(ci) == 1

    def test_with_expr_and_engine_is_symbolic(self, engine):
        ci = ConcolicInt(10, "y", engine)
        assert ci.is_symbolic()
        assert ci.expr == "y"
        assert ci.engine is engine

    def test_without_engine_is_concrete(self):
        ci = ConcolicInt(10)
        assert ci.is_concrete()
        assert ci.engine is None

    def test_from_string(self):
        ci = ConcolicInt("99")
        assert int(ci) == 99


class TestArithmetic:
    """Arithmetic operations produce correct concrete + symbolic results."""

    def test_add_two_concolic(self, engine):
        a = ConcolicInt(3, "a", engine)
        b = ConcolicInt(4, "b", engine)
        result = a + b
        assert unwrap_concolic(result) == 7
        assert result.expr == ["+", a, b]

    def test_add_concolic_and_primitive(self, engine):
        a = ConcolicInt(3, "a", engine)
        result = a + 10
        assert unwrap_concolic(result) == 13

    def test_reverse_add(self, engine):
        a = ConcolicInt(3, "a", engine)
        result = 10 + a
        assert unwrap_concolic(result) == 13

    def test_sub(self, engine):
        a = ConcolicInt(10, "a", engine)
        b = ConcolicInt(3, "b", engine)
        result = a - b
        assert unwrap_concolic(result) == 7
        assert result.expr == ["-", a, b]

    def test_mul(self, engine):
        a = ConcolicInt(5, "a", engine)
        b = ConcolicInt(4, "b", engine)
        result = a * b
        assert unwrap_concolic(result) == 20
        assert result.expr == ["*", a, b]

    def test_floor_div(self, engine):
        a = ConcolicInt(10, "a", engine)
        b = ConcolicInt(3, "b", engine)
        result = a // b
        assert unwrap_concolic(result) == 3

    def test_mod(self, engine):
        a = ConcolicInt(10, "a", engine)
        b = ConcolicInt(3, "b", engine)
        result = a % b
        assert unwrap_concolic(result) == 1

    def test_true_div_returns_float(self, engine):
        a = ConcolicInt(10, "a", engine)
        b = ConcolicInt(3, "b", engine)
        result = a / b
        assert isinstance(result, float)
        assert abs(unwrap_concolic(result) - 10 / 3) < 1e-10


class TestComparisons:
    """Comparison operations produce ConcolicBool with symbolic exprs."""

    def test_eq_true(self, engine):
        a = ConcolicInt(5, "a", engine)
        b = ConcolicInt(5, "b", engine)
        result = a == b
        assert unwrap_concolic(result) is True
        assert result.expr == ["=", a, b]

    def test_eq_false(self, engine):
        a = ConcolicInt(5, "a", engine)
        b = ConcolicInt(6, "b", engine)
        result = a == b
        assert unwrap_concolic(result) is False

    def test_lt(self, engine):
        a = ConcolicInt(3, "a", engine)
        b = ConcolicInt(5, "b", engine)
        result = a < b
        assert unwrap_concolic(result) is True
        assert result.expr == ["<", a, b]

    def test_le_equal(self, engine):
        a = ConcolicInt(5, "a", engine)
        b = ConcolicInt(5, "b", engine)
        result = a <= b
        assert unwrap_concolic(result) is True

    def test_gt(self, engine):
        a = ConcolicInt(5, "a", engine)
        b = ConcolicInt(3, "b", engine)
        result = a > b
        assert unwrap_concolic(result) is True
        assert result.expr == [">", a, b]

    def test_ge(self, engine):
        a = ConcolicInt(5, "a", engine)
        b = ConcolicInt(5, "b", engine)
        result = a >= b
        assert unwrap_concolic(result) is True

    def test_ne(self, engine):
        a = ConcolicInt(3, "a", engine)
        b = ConcolicInt(5, "b", engine)
        result = a != b
        assert unwrap_concolic(result) is True
        assert result.expr == ["not", ["=", a, b]]


class TestUnary:
    """Unary operations: abs, neg, pos."""

    def test_abs_positive(self, engine):
        ci = ConcolicInt(5, "x", engine)
        result = abs(ci)
        assert unwrap_concolic(result) == 5
        assert result.expr == ["abs", ci]

    def test_abs_negative(self, engine):
        ci = ConcolicInt(-5, "x", engine)
        result = abs(ci)
        assert unwrap_concolic(result) == 5

    def test_neg(self, engine):
        ci = ConcolicInt(5, "x", engine)
        result = -ci
        assert unwrap_concolic(result) == -5
        assert result.expr == ["-", ci]

    def test_pos_identity(self, engine):
        ci = ConcolicInt(5, "x", engine)
        result = +ci
        assert unwrap_concolic(result) == 5


class TestBitwise:
    """Bitwise operations: concrete-only, no symbolic tracking."""

    def test_and(self, engine):
        a = ConcolicInt(0b1100, "a", engine)
        b = ConcolicInt(0b1010, "b", engine)
        result = a & b
        assert unwrap_concolic(result) == 0b1000

    def test_or(self, engine):
        a = ConcolicInt(0b1100, "a", engine)
        b = ConcolicInt(0b1010, "b", engine)
        result = a | b
        assert unwrap_concolic(result) == 0b1110

    def test_xor(self, engine):
        a = ConcolicInt(0b1100, "a", engine)
        b = ConcolicInt(0b1010, "b", engine)
        result = a ^ b
        assert unwrap_concolic(result) == 0b0110

    def test_lshift(self, engine):
        ci = ConcolicInt(1, "x", engine)
        result = ci << 3
        assert unwrap_concolic(result) == 8

    def test_rshift(self, engine):
        ci = ConcolicInt(8, "x", engine)
        result = ci >> 2
        assert unwrap_concolic(result) == 2

    def test_invert(self, engine):
        ci = ConcolicInt(0, "x", engine)
        result = ~ci
        assert unwrap_concolic(result) == -1


class TestTypeConversion:
    """to_bool, to_int, to_float, to_str conversions."""

    def test_to_bool_zero_false(self, engine):
        ci = ConcolicInt(0, "x", engine)
        result = ci.to_bool()
        assert unwrap_concolic(result) is False

    def test_to_bool_nonzero_true(self, engine):
        ci = ConcolicInt(5, "x", engine)
        result = ci.to_bool()
        assert unwrap_concolic(result) is True

    def test_to_int_returns_self(self, engine):
        ci = ConcolicInt(42, "x", engine)
        assert ci.to_int() is ci

    def test_to_float_returns_concolic_float(self, engine):
        ci = ConcolicInt(42, "x", engine)
        cf = ci.to_float()
        assert isinstance(cf, ConcolicFloat)
        assert float(cf) == 42.0
        assert cf.expr == ["to_real", ci]

    def test_to_str_returns_concolic_str(self, engine):
        from pyct.core.str.str import ConcolicStr

        ci = ConcolicInt(42, "x", engine)
        cs = ci.to_str()
        assert isinstance(cs, ConcolicStr)

    def test_to_str_has_ite_expr(self, engine):
        ci = ConcolicInt(42, "x", engine)
        cs = ci.to_str()
        assert cs.expr[0] == "ite"
        assert cs.expr[1] == ["<", ci, "0"]

    def test_bool_builtin(self, engine):
        ci_zero = ConcolicInt(0, "x", engine)
        ci_nonzero = ConcolicInt(5, "y", engine)
        assert bool(ci_zero) is False
        assert bool(ci_nonzero) is True


class TestEdgeCases:
    """Zero, rounding identity, hash, pickle."""

    def test_zero(self, engine):
        ci = ConcolicInt(0, "x", engine)
        assert int(ci) == 0

    def test_rounding_identity(self, engine):
        import math

        ci = ConcolicInt(42, "x", engine)
        assert unwrap_concolic(math.ceil(ci)) == 42
        assert unwrap_concolic(math.floor(ci)) == 42
        assert unwrap_concolic(round(ci)) == 42
        assert unwrap_concolic(math.trunc(ci)) == 42

    def test_hash_consistent(self, engine):
        ci = ConcolicInt(42, "x", engine)
        assert hash(ci) == hash(42)

    def test_pickle_strips_engine(self, engine):
        ci = ConcolicInt(42, "x", engine)
        restored = pickle.loads(pickle.dumps(ci))
        assert int(restored) == 42
        assert restored.engine is None

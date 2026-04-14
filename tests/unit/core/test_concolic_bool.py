"""Tests for ConcolicBool."""

from __future__ import annotations

from pyct.core.bool import ConcolicBool
from pyct.core.float import ConcolicFloat
from pyct.core.int import ConcolicInt
from pyct.utils.concolic_converter import unwrap_concolic


class TestConstruction:
    """ConcolicBool creation from various value types."""

    def test_from_true(self, engine):
        cb = ConcolicBool(True, "x", engine)
        assert bool(cb) is True
        assert cb.is_symbolic()

    def test_from_false(self, engine):
        cb = ConcolicBool(False, "y", engine)
        assert int.__bool__(cb) is False

    def test_from_int_normalizes(self):
        assert int.__bool__(ConcolicBool(0)) is False
        assert int.__bool__(ConcolicBool(1)) is True

    def test_from_truthy_value(self):
        cb = ConcolicBool("nonempty")
        assert int.__bool__(cb) is True


class TestBoolConversion:
    """Standard Python protocol: __bool__, __int__, __float__, __str__."""

    def test_bool_returns_primitive(self, engine):
        cb = ConcolicBool(True, "x", engine)
        result = bool(cb)
        assert result is True
        assert type(result) is bool

    def test_bool_registers_branch(self, engine):
        cb = ConcolicBool(True, "x", engine)
        bool(cb)
        assert len(engine.path.branches) == 1

    def test_int_returns_zero_or_one(self):
        assert int(ConcolicBool(True)) == 1
        assert int(ConcolicBool(False)) == 0

    def test_float_returns_zero_or_one(self):
        assert float(ConcolicBool(True)) == 1.0
        assert float(ConcolicBool(False)) == 0.0

    def test_str_returns_true_false(self, engine):
        cb_true = ConcolicBool(True, "x", engine)
        cb_false = ConcolicBool(False, "y", engine)
        assert str(cb_true) == "True"
        assert str(cb_false) == "False"


class TestConcolicConversion:
    """Concolic conversions: to_bool, to_int, to_float, to_str."""

    def test_to_bool_returns_self(self, engine):
        cb = ConcolicBool(True, "x", engine)
        assert cb.to_bool() is cb

    def test_to_int_returns_concolic_int(self, engine):
        cb = ConcolicBool(True, "x", engine)
        ci = cb.to_int()
        assert isinstance(ci, ConcolicInt)
        assert int(ci) == 1

    def test_to_int_has_ite_expr(self, engine):
        cb = ConcolicBool(True, "x", engine)
        ci = cb.to_int()
        assert ci.expr == ["ite", cb, "1", "0"]

    def test_to_float_returns_concolic_float(self, engine):
        cb = ConcolicBool(True, "x", engine)
        cf = cb.to_float()
        assert isinstance(cf, ConcolicFloat)
        assert float(cf) == 1.0

    def test_to_float_has_ite_expr(self, engine):
        cb = ConcolicBool(False, "y", engine)
        cf = cb.to_float()
        assert cf.expr == ["ite", cb, "1.0", "0.0"]

    def test_to_str_returns_primitive(self, engine):
        cb = ConcolicBool(True, "x", engine)
        result = cb.to_str()
        assert result == "True"
        assert type(result) is str


class TestOperations:
    """XOR and other boolean operations."""

    def test_xor_symbolic_expr(self, engine):
        a = ConcolicBool(True, "a", engine)
        b = ConcolicBool(False, "b", engine)
        result = a ^ b
        assert unwrap_concolic(result) is True
        assert result.expr == ["xor", a, b]

    def test_xor_concrete_result(self):
        a = ConcolicBool(True)
        b = ConcolicBool(True)
        result = a ^ b
        assert unwrap_concolic(result) is False

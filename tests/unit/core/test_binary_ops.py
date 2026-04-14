"""Tests for BinaryOp enum, BinaryOperationHandler, and OperandConverter."""

from __future__ import annotations

from pyct.core.int import ConcolicInt
from pyct.core.operations.binary_ops import BinaryOp
from pyct.core.operations.converters import OperandConverter
from pyct.core.operations.handlers import BinaryOperationHandler
from pyct.utils.concolic_converter import unwrap_concolic


class TestBinaryOpEnum:
    """BinaryOp properties: is_division, is_comparison, is_reverse."""

    def test_add_properties(self):
        assert BinaryOp.ADD.method_name == "__add__"
        assert BinaryOp.ADD.smt_op == "+"
        assert not BinaryOp.ADD.is_division
        assert not BinaryOp.ADD.is_comparison
        assert not BinaryOp.ADD.is_reverse

    def test_truediv_is_division(self):
        assert BinaryOp.TRUEDIV.is_division
        assert not BinaryOp.TRUEDIV.is_comparison

    def test_eq_is_comparison(self):
        assert BinaryOp.EQ.is_comparison
        assert not BinaryOp.EQ.is_division

    def test_radd_is_reverse(self):
        assert BinaryOp.RADD.is_reverse

    def test_get_reverse_method(self):
        assert BinaryOp.ADD.get_reverse_method() == "__radd__"
        assert BinaryOp.LT.get_reverse_method() == "__gt__"
        assert BinaryOp.EQ.get_reverse_method() == "__eq__"


class TestBinaryOperationHandler:
    """Handler orchestrates concrete + symbolic computation."""

    def test_add_produces_symbolic_expr(self, engine):
        a = ConcolicInt(3, "a", engine)
        handler = BinaryOperationHandler(a)
        result = handler.execute(BinaryOp.ADD, ConcolicInt(4, "b", engine))
        assert unwrap_concolic(result) == 7
        assert result.expr == ["+", a, result.expr[2]]

    def test_ne_special_expression(self, engine):
        a = ConcolicInt(3, "a", engine)
        handler = BinaryOperationHandler(a)
        result = handler.execute(BinaryOp.NE, ConcolicInt(5, "b", engine))
        assert unwrap_concolic(result) is True
        assert result.expr[0] == "not"
        assert result.expr[1][0] == "="


class TestOperandConverter:
    """OperandConverter.to_concolic_numeric and validate_for_floor_division."""

    def test_convert_int_to_concolic(self, engine):
        result = OperandConverter.to_concolic_numeric(42, ConcolicInt, engine)
        assert isinstance(result, ConcolicInt)
        assert int(result) == 42

    def test_convert_bool_to_concolic(self, engine):
        result = OperandConverter.to_concolic_numeric(True, ConcolicInt, engine)
        assert isinstance(result, ConcolicInt)
        assert int(result) == 1

    def test_incompatible_returns_none(self, engine):
        result = OperandConverter.to_concolic_numeric("hello", ConcolicInt, engine)
        assert result is None

    def test_validate_floor_div_float_rejected(self):
        assert OperandConverter.validate_for_floor_division(1.5) is False

    def test_validate_floor_div_positive_int_accepted(self):
        assert OperandConverter.validate_for_floor_division(3) is True

    def test_validate_floor_div_negative_int_rejected(self):
        assert OperandConverter.validate_for_floor_division(-1) is False

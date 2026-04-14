"""Tests for BooleanExpressionBuilder and NumericExpressionBuilder."""

from __future__ import annotations

from pyct.core.expressions import (
    BooleanExpressionBuilder,
    NumericExpressionBuilder,
)


class TestBooleanExpressionBuilder:
    """Symbolic expression construction for boolean ops."""

    def test_xor(self):
        result = BooleanExpressionBuilder.xor("a", "b")
        assert result == ["xor", "a", "b"]

    def test_if_then_else(self):
        result = BooleanExpressionBuilder.if_then_else("cond", "1", "0")
        assert result == ["ite", "cond", "1", "0"]

    def test_logical_and(self):
        result = BooleanExpressionBuilder.logical_and("a", "b")
        assert result == ["and", "a", "b"]

    def test_logical_or(self):
        result = BooleanExpressionBuilder.logical_or("a", "b")
        assert result == ["or", "a", "b"]

    def test_logical_not(self):
        result = BooleanExpressionBuilder.logical_not("a")
        assert result == ["not", "a"]


class TestNumericExpressionBuilder:
    """Symbolic expression construction for numeric ops."""

    def test_int_literal(self):
        assert NumericExpressionBuilder.int_literal(42) == "42"

    def test_float_literal(self):
        assert NumericExpressionBuilder.float_literal(3.14) == "3.14"


class TestBooleanExpressionBuilderEdge:
    """Boundary and permissive-input characterization tests."""

    def test_xor_with_none_operand_accepted(self):
        # Builder does not validate inputs; produces a list with None.
        result = BooleanExpressionBuilder.xor(None, "b")
        assert result == ["xor", None, "b"]

    def test_if_then_else_with_nested_list_branches(self):
        result = BooleanExpressionBuilder.if_then_else("cond", ["+", 1, 2], ["-", 3, 4])
        assert result == ["ite", "cond", ["+", 1, 2], ["-", 3, 4]]

    def test_logical_not_with_symbolic_sub_expression(self):
        inner = BooleanExpressionBuilder.logical_and("a", "b")
        outer = BooleanExpressionBuilder.logical_not(inner)
        assert outer == ["not", ["and", "a", "b"]]


class TestNumericExpressionBuilderEdge:
    """Boundary inputs for numeric literal conversion."""

    def test_int_literal_zero(self):
        assert NumericExpressionBuilder.int_literal(0) == "0"

    def test_int_literal_negative(self):
        # str(-42) is "-42" — builder does not wrap negatives in SMT (- n) form.
        # This characterization lets solver/formula_builder stay responsible
        # for SMT-negation formatting.
        assert NumericExpressionBuilder.int_literal(-42) == "-42"

    def test_float_literal_infinity(self):
        assert NumericExpressionBuilder.float_literal(float("inf")) == "inf"

    def test_float_literal_nan(self):
        assert NumericExpressionBuilder.float_literal(float("nan")) == "nan"

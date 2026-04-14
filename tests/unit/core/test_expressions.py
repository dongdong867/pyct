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

from __future__ import annotations

from typing import Any, List, Union

# Type alias for symbolic expressions
SymbolicExpr = List[Union[str, Any]]


class BooleanExpressionBuilder:
    """Builds symbolic expressions for boolean operations."""

    @staticmethod
    def xor(left: Any, right: Any) -> SymbolicExpr:
        """
        Create XOR expression.

        Args:
            left: Left operand
            right: Right operand

        Returns:
            Symbolic expression representing XOR operation
        """
        return ["xor", left, right]

    @staticmethod
    def if_then_else(
        condition: Any, true_branch: str, false_branch: str
    ) -> SymbolicExpr:
        """
        Create if-then-else expression.

        Args:
            condition: Boolean condition
            true_branch: Value if condition is true
            false_branch: Value if condition is false

        Returns:
            Symbolic expression representing ITE operation
        """
        return ["ite", condition, true_branch, false_branch]

    @staticmethod
    def logical_and(left: Any, right: Any) -> SymbolicExpr:
        """Create AND expression."""
        return ["and", left, right]

    @staticmethod
    def logical_or(left: Any, right: Any) -> SymbolicExpr:
        """Create OR expression."""
        return ["or", left, right]

    @staticmethod
    def logical_not(operand: Any) -> SymbolicExpr:
        """Create NOT expression."""
        return ["not", operand]


class NumericExpressionBuilder:
    """Builds symbolic expressions for numeric operations."""

    @staticmethod
    def int_literal(value: int) -> str:
        """Create integer literal expression."""
        return str(value)

    @staticmethod
    def float_literal(value: float) -> str:
        """Create float literal expression."""
        return str(value)
